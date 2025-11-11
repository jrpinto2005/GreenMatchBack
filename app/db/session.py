# app/db/session.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env (solo en local)
load_dotenv()

# === Configuración de entorno ===
DB_USER = os.getenv("DB_USER", "appuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "plant_app_db")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "5432")

# Conector de Cloud SQL (solo si estamos en Cloud Run)
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME")

# === Construcción dinámica de la URL de conexión ===
if INSTANCE_CONNECTION_NAME:
    # Entorno: Cloud Run con Cloud SQL Connector
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@/{DB_NAME}"
        f"?host=/cloudsql/{INSTANCE_CONNECTION_NAME}"
    )
else:
    # Entorno: desarrollo local o servidor sin Cloud SQL
    SQLALCHEMY_DATABASE_URL = (
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

# === Crear motor y sesión ===
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Verifica conexiones antes de usarlas
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# === Dependencia para FastAPI ===
def get_db():
    """Devuelve una sesión de base de datos para usar en dependencias."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Debug opcional: imprimir la URL de conexión (solo en desarrollo)
if not INSTANCE_CONNECTION_NAME:
    print(f"Conectando localmente a: {SQLALCHEMY_DATABASE_URL}")
else:
    print(f"Conectando a Cloud SQL vía socket: /cloudsql/{INSTANCE_CONNECTION_NAME}")
