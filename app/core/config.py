# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # SOLO cosas de Vertex AI aquí
    project_id: str
    vertex_location: str = "us-central1"
    vertex_model_name: str = "gemini-1.5-pro"

    # Importante: ignorar variables extra del .env (db_user, db_password, etc.)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  #  clave para que no se queje por db_user, region, etc.
    )


settings = Settings()
