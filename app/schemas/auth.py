from pydantic import BaseModel, EmailStr
from typing import Optional


class AuthResponse(BaseModel):
    ok: bool
    message: str
    user_id: Optional[int] = None
    token: Optional[str] = None


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    username: str
    password: str


class LoginRequest(BaseModel):
    identifier: str  # username o email
    password: str


class ResetPasswordRequest(BaseModel):
    identifier: str  # username o email
    new_password: str
