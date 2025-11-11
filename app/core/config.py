# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Proyecto y Vertex AI
    project_id: str
    vertex_location: str
    vertex_model_name: str

    # Base de datos (opcionales aquí; en session.py ya usamos os.getenv directamente)
    db_user: str = "appuser"
    db_password: str = "TU_PASSWORD_AQUI"
    db_name: str = "plant_app_db"
    db_host: str | None = None
    db_port: int | None = None

    # Cloud SQL (para Cloud Run)
    instance_connection_name: str | None = None

    # Otros campos que ya tienes en tu .env
    region: str | None = None
    gcs_bucket: str | None = None

    # Auth sencilla
    auth_secret: str = "change_me"
    password_salt: str = "change_me"

    # Configuración de Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 👈 Ignora cualquier variable adicional que no esté declarada
    )


settings = Settings()
