from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db import models
from app.schemas.auth import (
    AuthResponse,
    RegisterRequest,
    LoginRequest,
    ResetPasswordRequest,
)
from app.core.security import hash_password, verify_password, create_access_token


router = APIRouter()


@router.post("/register", response_model=AuthResponse)
def register_user(payload: RegisterRequest, db: Session = Depends(get_db)):
    # ¿Existe ya el username?
    existing_username = (
        db.query(models.User)
        .filter(models.User.username == payload.username)
        .first()
    )
    if existing_username:
        return AuthResponse(
            ok=False,
            message="El nombre de usuario ya está en uso.",
        )

    # ¿Existe ya el email?
    existing_email = (
        db.query(models.User)
        .filter(models.User.email == payload.email)
        .first()
    )
    if existing_email:
        return AuthResponse(
            ok=False,
            message="El correo electrónico ya está registrado.",
        )

    # Crear usuario
    user = models.User(
        name=payload.name,
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user_id=user.id)

    return AuthResponse(
        ok=True,
        message="Usuario registrado correctamente.",
        user_id=user.id,
        token=token,
    )


@router.post("/login", response_model=AuthResponse)
def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    # Buscar por username o email
    user = (
        db.query(models.User)
        .filter(
            (models.User.username == payload.identifier)
            | (models.User.email == payload.identifier)
        )
        .first()
    )

    if not user or not user.password_hash:
        return AuthResponse(
            ok=False,
            message="Usuario o contraseña incorrectos.",
        )

    if not verify_password(payload.password, user.password_hash):
        return AuthResponse(
            ok=False,
            message="Usuario o contraseña incorrectos.",
        )

    token = create_access_token(user_id=user.id)

    return AuthResponse(
        ok=True,
        message="Inicio de sesión exitoso.",
        user_id=user.id,
        token=token,
    )


@router.post("/reset", response_model=AuthResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    # Buscar usuario por username o email
    user = (
        db.query(models.User)
        .filter(
            (models.User.username == payload.identifier)
            | (models.User.email == payload.identifier)
        )
        .first()
    )

    if not user:
        return AuthResponse(
            ok=False,
            message="No se encontró un usuario con ese identificador.",
        )

    user.password_hash = hash_password(payload.new_password)
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        ok=True,
        message="Contraseña actualizada correctamente.",
        user_id=user.id,
    )
