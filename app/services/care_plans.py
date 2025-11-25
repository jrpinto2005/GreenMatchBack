# app/services/care_plans.py
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.db import models
from app.core.vertex_client import generate_gemini_response


# --------- Esquema del plan (valida estructura, sin inventar) ---------
class FreqDetail(BaseModel):
    frecuencia: str = Field(default="")
    detalle: str = Field(default="")

class CarePlanSchema(BaseModel):
    riego: FreqDetail
    luz: FreqDetail
    temperatura: str
    humedad: str
    fertilizacion: FreqDetail
    poda: str
    plagas: str
    alertas: list[str]


# --------- Utils ---------
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)

def _clean_json_text(text: str) -> str:
    """Quita fences tipo ```json ... ``` o ``` ... ``` y recorta al primer {...} último }."""
    cleaned = FENCE_RE.sub("", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end+1]
    return cleaned


def _build_prompt(plant_common_name: str, context_block: str) -> str:
    return f"""
Eres un experto en jardinería. Devuelve **SOLO** un JSON válido (sin explicaciones, sin markdown).
Planta: {plant_common_name}
{context_block}

Formato EXACTO que debes devolver (rellena todos los campos; usa "" si no aplica, pero NO agregues texto fuera del JSON):
{{
  "riego": {{"frecuencia":"", "detalle":""}},
  "luz": {{"tipo":"", "detalle":""}},
  "temperatura": "",
  "humedad": "",
  "fertilizacion": {{"frecuencia":"", "detalle":""}},
  "poda": "",
  "plagas": "",
  "alertas": []
}}
""".strip()


# --------- Servicio principal (estricto, sin fallback inventado) ---------
def ensure_care_plan_for_plant(
    db: Session,
    user_id: int,
    plant: models.Plant,
    session_id: Optional[int] = None,
) -> Optional[models.CarePlan]:
    """
    Crea (si no existe) un CarePlan para la planta dada del usuario.
    - Idempotente por (user_id, plant_id).
    - SOLO guarda si el modelo devuelve JSON válido según CarePlanSchema.
    - Si el JSON es inválido o no parsea, retorna None (no inventa contenido).
    """
    if not user_id or not plant or not plant.id:
        raise ValueError("user_id y plant.id son obligatorios para generar el CarePlan.")

    existing = (
        db.query(models.CarePlan)
        .filter(
            models.CarePlan.user_id == user_id,
            models.CarePlan.plant_id == plant.id,
        )
        .order_by(models.CarePlan.created_at.desc())
        .first()
    )
    if existing:
        return existing

    # Construir contexto para el prompt (sin asumir nada extra)
    ctx_lines = []
    if plant.location:    ctx_lines.append(f"Ubicación: {plant.location}")
    if plant.light:       ctx_lines.append(f"Luz: {plant.light}")
    if plant.humidity:    ctx_lines.append(f"Humedad: {plant.humidity}")
    if plant.temperature: ctx_lines.append(f"Temperatura: {plant.temperature}")
    context_block = "\n".join(ctx_lines)

    prompt = _build_prompt(plant.common_name.strip(), context_block)

    # Llamada al modelo
    raw_text = generate_gemini_response(prompt)

    # Intento 1: limpiar fences y parsear
    try:
        cleaned = _clean_json_text(raw_text)
        parsed = json.loads(cleaned)
        plan_model = CarePlanSchema(**parsed)
    except (json.JSONDecodeError, ValidationError):
        # Intento 2 (último): probar el raw por si el recorte eliminó algo útil
        try:
            parsed2 = json.loads(raw_text)
            plan_model = CarePlanSchema(**parsed2)
        except Exception:
            # No guardamos nada si no hay JSON válido
            return None

    cp = models.CarePlan(
        session_id=session_id,
        user_id=user_id,
        plant_id=plant.id,               
        plant_name=plant.common_name,
        environment_json={
            "location": plant.location,
            "light": plant.light,
            "humidity": plant.humidity,
            "temperature": plant.temperature,
        },
        plan_json=plan_model.model_dump(),  
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp
