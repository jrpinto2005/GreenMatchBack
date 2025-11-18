# app/core/vertex_client.py
import json
from typing import Iterable, List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Part
from app.core.config import settings

# Init global
vertexai.init(
    project=settings.project_id,
    location=settings.vertex_location,
)
model = GenerativeModel(settings.vertex_model_name)


# -------------------------------------------------
# 1. Texto plano
# -------------------------------------------------
def generate_gemini_response(prompt: str) -> str:
    """Llama a Gemini para generar una respuesta en texto plano (solo prompt de texto)."""
    response = model.generate_content(prompt)

    # Intentar usar response.text
    try:
        if getattr(response, "text", None):
            return response.text
    except Exception:
        pass

    # Parseo manual de candidates/parts
    if not response.candidates:
        raise ValueError("La respuesta de Vertex AI no contiene candidatos.")

    candidate = response.candidates[0]
    parts = getattr(candidate.content, "parts", []) or []

    texts = []
    for p in parts:
        text = getattr(p, "text", None)
        if text:
            texts.append(text)

    if not texts:
        raise ValueError("No se encontraron partes de texto en la respuesta de Vertex AI.")

    return "".join(texts)


# -------------------------------------------------
# 2. NUEVO: Texto + imágenes (GCS URIs)
# -------------------------------------------------
def generate_gemini_response_with_images(
    prompt: str,
    image_gcs_uris: Optional[List[str]] = None,
) -> str:
    """
    Llama a Gemini con un prompt de texto + hasta N imágenes (por ahora máx 3).
    Cada imagen se pasa como Part con referencia a GCS:
      - gs://bucket/path/to/image.jpg

    Úsalo cuando quieras que el modelo tenga en cuenta las fotos del usuario
    (identificación de planta, manchas en hojas, etc).
    """
    image_gcs_uris = image_gcs_uris or []
    # Por si acaso, limitamos a 3 aquí también
    image_gcs_uris = image_gcs_uris[:3]

    # Construir la lista de parts: primero las imágenes, luego el texto
    parts: List[Part] = []

    for uri in image_gcs_uris:
        # Part.from_uri crea un part que referencia un archivo en GCS
        parts.append(
            Part.from_uri(
                uri=uri,
                mime_type="image/jpeg",  # si usas png cambia a image/png o detecta según extensión
            )
        )

    # Por último, el prompt de texto
    parts.append(Part.from_text(prompt))

    response = model.generate_content(parts)

    # Igual que en la función de texto
    try:
        if getattr(response, "text", None):
            return response.text
    except Exception:
        pass

    if not response.candidates:
        raise ValueError("La respuesta de Vertex AI no contiene candidatos.")

    candidate = response.candidates[0]
    cparts = getattr(candidate.content, "parts", []) or []

    texts = []
    for p in cparts:
        text = getattr(p, "text", None)
        if text:
            texts.append(text)

    if not texts:
        raise ValueError("No se encontraron partes de texto en la respuesta de Vertex AI.")

    return "".join(texts)


# -------------------------------------------------
# 3. Análisis de intención
# -------------------------------------------------
def analyze_user_message(
    history_text: str,
    session_context: dict,
    new_message: str,
) -> dict:
    """
    Usa Gemini para:
    - determinar el 'mode': 'general', 'recommend', 'care_plan', 'identify'
    - extraer campos: location, time, humidity, light, temperature, plant_name
    - indicar si falta información y qué pregunta de aclaración hacer
    Devuelve un dict con esa estructura.
    """

    context_str = json.dumps(session_context, ensure_ascii=False)

    analysis_prompt = f"""
Eres un asistente que SOLO clasifica y extrae información estructurada de mensajes de usuario
relacionados con plantas y jardinería. NO debes generar la respuesta final al usuario, solo análisis.

Tipos de petición posibles (mode):
- "recommend": el usuario quiere recomendaciones de plantas para ciertas condiciones.
- "care_plan": el usuario quiere un plan de cuidado para una planta específica.
- "identify": el usuario quiere identificar qué planta tiene (por texto, o luego por imagen).
- "general": cualquier otra pregunta o charla sobre plantas.

Información importante:
- Historial reciente de la conversación (puede estar vacío):
{history_text}

- Contexto ya conocido de la sesión (puede estar vacío):
{context_str}

- Mensaje actual del usuario:
\"\"\"{new_message}\"\"\"


TU TAREA:
1. Decide el "mode" más adecuado entre: "recommend", "care_plan", "identify", "general".
2. Intenta extraer o inferir (en español):
   - "location": ciudad, tipo de lugar ("Bogotá, apartamento", "terraza en Medellín", etc.)
   - "time": si es relevante, momento del día o periodo (por ejemplo "día", "noche", "todo el año"). Si no se sabe, pon null.
   - "humidity": "baja", "media" o "alta" si se puede inferir; si no, null.
   - "light": tipo de luz: "baja", "media", "alta", "luz indirecta", etc. Si no se sabe, null.
   - "temperature": rango aproximado en °C o descripción corta, si se puede inferir; si no, null.
   - "plant_name": solo para "care_plan" o "identify" si se menciona una planta concreta (nombre común o científico). Si no, null.

3. Para cada mode, campos mínimos recomendados:
   - recommend: location, light, humidity (y si es posible interior/exterior en 'light' o en la descripción).
   - care_plan: plant_name, location, light, humidity.
   - identify: plant_name solo si el usuario la menciona; si no, puede ser null.
   - general: no requiere campos extra.

4. Si el mode requiere campos mínimos y NO puedes obtenerlos ni del mensaje ni del historial,
   marca "need_clarification": true, lista los "missing_fields" y propone una "clarification_question"
   en español, dirigida al usuario, corta y directa, para pedir solo los datos que faltan.

5. Si NO hace falta aclaración, pon:
   - "need_clarification": false
   - "missing_fields": []
   - "clarification_question": null

RESPONDE EXCLUSIVAMENTE con un JSON válido en una sola línea,
SIN texto adicional, SIN comentarios, SIN markdown.

Ejemplo de formato EXACTO:

{{
  "mode": "recommend",
  "location": "Bogotá, apartamento",
  "time": null,
  "humidity": "media",
  "light": "baja",
  "temperature": null,
  "plant_name": null,
  "need_clarification": false,
  "missing_fields": [],
  "clarification_question": null
}}

Ahora genera SOLO el JSON para este caso.
"""

    # Aquí seguimos usando solo texto, no imágenes
    raw = model.generate_content(analysis_prompt)
    analysis_text = generate_gemini_response(analysis_prompt)

    try:
        data = json.loads(analysis_text)
    except json.JSONDecodeError:
        # fallback muy simple si algo falla: modo general sin aclaración
        return {
            "mode": "general",
            "location": None,
            "time": None,
            "humidity": None,
            "light": None,
            "temperature": None,
            "plant_name": None,
            "need_clarification": False,
            "missing_fields": [],
            "clarification_question": None,
        }

    # Nos aseguramos de que todas las claves existan
    defaults = {
        "mode": "general",
        "location": None,
        "time": None,
        "humidity": None,
        "light": None,
        "temperature": None,
        "plant_name": None,
        "need_clarification": False,
        "missing_fields": [],
        "clarification_question": None,
    }
    for k, v in defaults.items():
        data.setdefault(k, v)

    return data
