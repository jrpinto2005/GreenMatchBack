import hashlib
from datetime import datetime, timedelta
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    """
    Hash muy simple con SHA256 + salt.
    No es producción, pero suficiente para este proyecto.
    """
    salted = password + settings.password_salt
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_access_token(user_id: int, expires_minutes: int = 60 * 24) -> str:
    """
    Crea un JWT simple con el user_id.
    """
    now = datetime.utcnow()
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=expires_minutes),
        "iat": now,
    }
    token = jwt.encode(payload, settings.auth_secret, algorithm="HS256")
    return token
