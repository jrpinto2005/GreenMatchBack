# app/api/chat.py (al inicio del archivo)
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any, Literal

from app.db.session import get_db
from app.db import models
from app.core.vertex_client import (
    generate_gemini_response,
    analyze_user_message,
)
from app.services.care_plans import ensure_care_plan_for_plant
from app.services.plants import ensure_plant_for_user


router = APIRouter()


class ChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str
    user_id: Optional[int] = None  # Para crear sesión si no existe


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
    created_at: datetime

    class Config:
        orm_mode = True
@router.post("/message", response_model=ChatResponse)
def chat_message(payload: ChatRequest, db: Session = Depends(get_db)):
    # 1. Obtener o crear sesión
    session: Optional[models.ChatSession] = None
    if payload.session_id is not None:
        session = db.query(models.ChatSession).get(payload.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = models.ChatSession(
            user_id=payload.user_id
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    # 2. Guardar mensaje del usuario
    user_msg = models.ChatMessage(
        
        session_id=session.id,
        sender="user",
        content=payload.message,
        message_type="text",
    )
    db.add(user_msg)
    
    session.last_activity_at = datetime.utcnow()
    db.add(session)
    db.commit()
    db.refresh(user_msg)

    # 3. Historial reciente de la sesión
    last_messages = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.session_id == session.id)
        .order_by(models.ChatMessage.created_at.asc())
        .all()
    )

    history_text_parts = []
    for m in last_messages[-6:]:
        role = "Usuario" if m.sender == "user" else "Asistente"
        if m.content:
            history_text_parts.append(f"{role}: {m.content}")
    history_text = "\n".join(history_text_parts)

    # 4. Contexto de sesión: lo que ya sabemos
    session_context = {
        "location": session.location,
        "environment": session.environment_json,
    }

    # 5. Análisis con Gemini: intención + extracción
    analysis = analyze_user_message(
        history_text=history_text,
        session_context=session_context,
        new_message=payload.message,
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
    if humidity:
        if env.get("humidity") != humidity:
            env["humidity"] = humidity
            changed_env = True
    if light:
        if env.get("light") != light:
            env["light"] = light
            changed_env = True
    if temperature:
        if env.get("temperature") != temperature:
            env["temperature"] = temperature
            changed_env = True
    if time_info:
        if env.get("time") != time_info:
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
        # Crear/Asegurar planta con datos inferidos
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

        # Si la intención fue "care_plan", generar y guardar el plan ahora
        if mode == "care_plan":
            try:
                created_plan = ensure_care_plan_for_plant(
                    db=db,
                    user_id=owner_user_id,
                    plant=created_plant,
                    session_id=session.id,
                )
            except Exception:
                # Falla silenciosa del plan no debe impedir la conversación
                created_plan = None
                
    # 7. Si tenemos suficiente info, construimos el prompt especializado
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
            "El usuario quiere identificar qué planta tiene, usando la información disponible "
            "en el texto y el historial. Si no se puede identificar con certeza, ofrece "
            "posibles candidatos y explica la incertidumbre."
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

    full_prompt = f"""
Eres un asistente experto en plantas y jardinería. Siempre respondes en español, de forma clara y estructurada.

Instrucción de modo:
{mode_instruction}

Información del contexto:
{context_block}

Historial reciente de la conversación:
{history_text}

Mensaje actual del usuario:
Usuario: {payload.message}

Responde solo con el mensaje que le dirías al usuario, en un tono cercano pero profesional.
No menciones que hiciste un análisis de intención ni que convertiste nada a JSON.
"""

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

@router.get("/sessions", response_model=List[ConversationSummary])
def list_user_sessions(user_id: int, db: Session = Depends(get_db)):
    """
    Lista las conversaciones (ChatSession) de un usuario, ordenadas por última actividad.
    Siempre devuelve una lista (posiblemente vacía).
    """
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == user_id)
        .order_by(models.ChatSession.last_activity_at.desc())
        .all()
    )

    summaries: List[ConversationSummary] = []

    for s in sessions:
        # Primer mensaje de usuario como título resumido
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
    """
    Devuelve todos los mensajes de una conversación.
    """
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



