# app/services/storage.py
import time
import uuid
from typing import Optional

from google.cloud import storage
from app.core.config import settings

_storage_client: Optional[storage.Client] = None

def get_storage_client() -> storage.Client:
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(
            project=settings.project_id  
        )
    return _storage_client

def upload_chat_image(
    data: bytes,
    content_type: str,
    user_id: int,
    session_id: int,
    idx: int,
) -> str:
    """
    Sube una imagen al bucket configurado y devuelve la URL pública.
    """
    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket)

    ts = int(time.time())
    file_id = uuid.uuid4().hex[:8]

    # Ruta organizada por usuario/sesión
    blob_name = f"fotos_chat/user-{user_id}/session-{session_id}/{ts}_{idx}_{file_id}"

    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)

    gcs_uri = f"gs://{settings.gcs_bucket}/{blob_name}"
    return gcs_uri

def upload_plant_image(
    data: bytes,
    content_type: str,
    user_id: int,
    plant_id: int,
) -> str:
    """
    Sube la imagen principal de una planta al mismo bucket,
    pero en la carpeta foto_planta/, y devuelve la URI gs://.
    """
    client = get_storage_client()
    bucket = client.bucket(settings.gcs_bucket)

    ts = int(time.time())
    file_id = uuid.uuid4().hex[:8]

    # Ruta organizada por usuario/planta
    blob_name = f"foto_planta/user-{user_id}/plant-{plant_id}/{ts}_{file_id}"

    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)

    gcs_uri = f"gs://{settings.gcs_bucket}/{blob_name}"
    return gcs_uri