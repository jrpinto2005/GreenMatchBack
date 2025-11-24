# app/api/chat.py
from datetime import datetime
from typing import Optional, List


from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.core.vertex_client import (
    generate_gemini_response,
    analyze_user_message,
    generate_gemini_response_with_images,  # NUEVO
)
from app.services.care_plans import ensure_care_plan_for_plant
from app.services.plants import ensure_plant_for_user
from app.services.storage import upload_chat_image

router = APIRouter()


# ------------ Schemas ------------

class ChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str
    user_id: Optional[int] = None  # Para crear sesión si no existe
    image_uris: Optional[list[str]] = None  # NUEVO: urls de imágenes adjuntas


class ChatResponse(BaseModel):
    session_id: int
    reply: str


class ConversationSummary(BaseModel):
    id: int
    started_at: datetime
    last_activity_at: datetime
    title: str | None

    model_config = {
        "from_attributes": True
    }


class MessageOut(BaseModel):
    id: int
    session_id: int
    sender: str
    content: str | None
    message_type: str
    image_gcs_uris: List[str] | None
    created_at: datetime

    class Config:
        orm_mode = True


# ------------ Mensaje de chat (texto + imágenes ya subidas) ------------

@router.post("/message", response_model=ChatResponse)
def chat_message(payload: ChatRequest, db: Session = Depends(get_db)):
    # 1. Obtener o crear sesión
    session: Optional[models.ChatSession] = None
    if payload.session_id is not None:
        session = db.query(models.ChatSession).get(payload.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = models.ChatSession(user_id=payload.user_id)
        db.add(session)
        db.commit()
        db.refresh(session)

    # 2. Guardar mensaje del usuario
    user_msg = models.ChatMessage(
        session_id=session.id,
        sender="user",
        content=payload.message,
        message_type="text" if not payload.image_uris else "mixed",
        image_gcs_uris=payload.image_uris or None,
    )
    db.add(user_msg)

    session.last_activity_at = datetime.utcnow()
    db.add(session)
    db.commit()
    db.refresh(user_msg)

    # 3. Historial reciente de la sesión (incluye nota de imágenes)
    last_messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

    history_text_parts = []
    for m in last_messages[-6:]:
        role = "Usuario" if m.sender == "user" else "Asistente"

        img_note = ""
        if getattr(m, "image_gcs_uris", None):
            img_note = f"[Adjuntó {len(m.image_gcs_uris)} imagen(es)] "

        text = (m.content or "").strip()
        if img_note or text:
            history_text_parts.append(f"{role}: {img_note}{text}")

    history_text = "\n".join(history_text_parts)

    # 4. Contexto de sesión: lo que ya sabemos
    session_context = {
        "location": session.location,
        "environment": session.environment_json,
    }

    # 5. Análisis con Gemini: intención + extracción
    #    Le contamos explícitamente si este mensaje trae fotos
    if payload.image_uris:
        new_message_for_analysis = (
            f"{payload.message} [El usuario adjuntó {len(payload.image_uris)} "
            f"imagen(es) de la planta para ayudar a identificarla.]"
        )
    else:
        new_message_for_analysis = payload.message

    analysis = analyze_user_message(
        history_text=history_text,
        session_context=session_context,
        new_message=new_message_for_analysis,
    )


    mode = analysis["mode"]
    location = analysis["location"]
    time_info = analysis["time"]
    humidity = analysis["humidity"]
    light = analysis["light"]
    temperature = analysis["temperature"]
    plant_name = analysis["plant_name"]
    need_clarification = analysis["need_clarification"]
    missing_fields = analysis["missing_fields"]
    clarification_question = analysis["clarification_question"]

    # Actualizar sesión con info nueva si no la teníamos
    updated = False
    if location and session.location != location:
        session.location = location
        updated = True

    env = session.environment_json or {}
    changed_env = False
    if humidity and env.get("humidity") != humidity:
        env["humidity"] = humidity
        changed_env = True
    if light and env.get("light") != light:
        env["light"] = light
        changed_env = True
    if temperature and env.get("temperature") != temperature:
        env["temperature"] = temperature
        changed_env = True
    if time_info and env.get("time") != time_info:
        env["time"] = time_info
        changed_env = True

    if changed_env:
        session.environment_json = env
        updated = True

    if updated:
        db.add(session)
        db.commit()

    # 6. Si falta información crítica: hacemos pregunta de aclaración
    if need_clarification and clarification_question:
        reply_text = clarification_question

        assistant_msg = models.ChatMessage(
            session_id=session.id,
            sender="assistant",
            content=reply_text,
            message_type="text",
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        return ChatResponse(session_id=session.id, reply=reply_text)

    # 6.5 Auto-crear planta (y opcionalmente el care plan) ANTES de generar la respuesta
    created_plant = None
    created_plan = None

    owner_user_id = payload.user_id or session.user_id
    if owner_user_id and plant_name and not need_clarification:
        created_plant = ensure_plant_for_user(
            db=db,
            user_id=owner_user_id,
            common_name=plant_name,
            source="chat",
            light=light,
            humidity=humidity,
            temperature=temperature,
            location=location,
        )

        if mode == "care_plan":
            try:
                created_plan = ensure_care_plan_for_plant(
                    db=db,
                    user_id=owner_user_id,
                    plant=created_plant,
                    session_id=session.id,
                )
            except Exception:
                created_plan = None

    # 7. Construir el prompt especializado
    mode_instruction = {
        "general": (
            "Responde como un asistente experto en plantas, contestando dudas generales "
            "sobre plantas, cuidado y recomendaciones."
        ),
        "recommend": (
            "El usuario quiere recomendaciones de plantas que se adapten a sus condiciones "
            "de ubicación y ambiente. Propón varias opciones y explica por qué son adecuadas."
        ),
        "care_plan": (
            "El usuario quiere un plan de cuidado detallado para una planta concreta, "
            "adaptado a su ubicación y condiciones."
        ),
        "identify": (
            "El usuario quiere identificar qué planta tiene usando la información de texto "
            "y especialmente las imágenes adjuntas. Describe tu razonamiento de forma clara "
            "y si no estás seguro dilo explícitamente, ofrece candidatos probables y la razón."
        ),
    }.get(mode, "Responde como un asistente experto en plantas.")

    context_lines = []
    if location:
        context_lines.append(f"Ubicación del usuario: {location}")
    if light:
        context_lines.append(f"Condiciones de luz: {light}")
    if humidity:
        context_lines.append(f"Condiciones de humedad: {humidity}")
    if temperature:
        context_lines.append(f"Temperatura típica: {temperature}")
    if time_info:
        context_lines.append(f"Marco temporal relevante: {time_info}")
    if plant_name:
        context_lines.append(f"Planta objetivo: {plant_name}")

    context_block = "\n".join(context_lines)

    # Nota textual sobre imágenes del mensaje actual (opcional, solo contexto semántico)
    images_line = ""
    if payload.image_uris:
        images_line = (
            f"\nEl usuario adjuntó {len(payload.image_uris)} imagen(es) de su planta."
        )

    full_prompt = f"""
Eres un asistente experto en plantas y jardinería. Siempre respondes en español, de forma clara y estructurada.

Instrucción de modo:
{mode_instruction}

Información del contexto:
{context_block}

Historial reciente de la conversación:
{history_text}

Mensaje actual del usuario:
Usuario: {payload.message}{images_line}

Responde solo con el mensaje que le dirías al usuario, en un tono cercano pero profesional.
No menciones que hiciste un análisis de intención ni que convertiste nada a JSON.
"""

    # 🔥 AQUÍ VIENE EL CAMBIO IMPORTANTE 🔥
    # Si hay imágenes y el modo es "identify", usamos la función multimodal.
    if payload.image_uris and mode == "identify":
        reply_text = generate_gemini_response_with_images(
            full_prompt,
            image_gcs_uris=payload.image_uris,  # las gs:// que guardaste en DB
        )
    else:
        reply_text = generate_gemini_response(full_prompt)

    # 7.5 Anexar confirmación visible al usuario sobre la creación
    if created_plan:
        reply_text += "... guardé su plan de cuidado ..."
    elif created_plant:
        reply_text += "... pulsa **Crear plan** ..."

    # 8. Guardar respuesta del asistente
    assistant_msg = models.ChatMessage(
        session_id=session.id,
        sender="assistant",
        content=reply_text,
        message_type="text",
    )
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return ChatResponse(session_id=session.id, reply=reply_text)


# ------------ Listado de sesiones y mensajes ------------

@router.get("/sessions", response_model=List[ConversationSummary])
def list_user_sessions(user_id: int, db: Session = Depends(get_db)):
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == user_id)
        .order_by(models.ChatSession.last_activity_at.desc())
        .all()
    )

    summaries: List[ConversationSummary] = []

    for s in sessions:
        first_user_msg = (
            db.query(models.ChatMessage)
            .filter(
                models.ChatMessage.session_id == s.id,
                models.ChatMessage.sender == "user",
            )
            .order_by(models.ChatMessage.created_at.asc())
            .first()
        )

        if first_user_msg and first_user_msg.content:
            raw_title = first_user_msg.content.strip()
            title = raw_title[:50] + "…" if len(raw_title) > 50 else raw_title
        else:
            title = f"Conversación #{s.id}"

        summaries.append(
            ConversationSummary(
                id=s.id,
                started_at=s.started_at,
                last_activity_at=s.last_activity_at,
                title=title,
            )
        )

    return summaries


@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_session_messages(session_id: int, db: Session = Depends(get_db)):
    session = db.query(models.ChatSession).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    msgs = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session_id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

    return msgs


# ------------ Upload de imágenes (GCS) ------------

@router.post("/upload-images")
async def upload_chat_images(
    user_id: int = Form(...),
    session_id: int | None = Form(None),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    """
    Sube hasta 3 imágenes al bucket y crea un ChatMessage con esas imágenes.
    Devuelve: session_id, lista de URLs y id del mensaje.
    """
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Debes enviar al menos 1 imagen.")
    if len(files) > 3:
        raise HTTPException(status_code=400, detail="Máximo 3 imágenes por mensaje.")

    # 1) Asegurar existencia de sesión (igual que en /chat/message)
    if session_id is not None:
        session = db.query(models.ChatSession).get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = models.ChatSession(user_id=user_id)
        db.add(session)
        db.commit()
        db.refresh(session)

    # 2) Subir todas las imágenes
    image_urls: list[str] = []
    for idx, f in enumerate(files):
        content = await f.read()
        url = upload_chat_image(
            data=content,
            content_type=f.content_type or "image/jpeg",
            user_id=user_id,
            session_id=session.id,
            idx=idx,
        )
        image_urls.append(url)

    # 3) Crear ChatMessage “solo imágenes”
    msg = models.ChatMessage(
        session_id=session.id,
        sender="user",
        content=None,
        message_type="image",
        image_gcs_uris=image_urls,
    )
    db.add(msg)

    session.last_activity_at = datetime.utcnow()
    db.add(session)
    db.commit()
    db.refresh(msg)

    return {
        "session_id": session.id,
        "image_urls": image_urls,
        "message_id": msg.id,
    }

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(models.ChatSession).get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")


    db.delete(session)
    db.commit()
    return