"""Hashing de contrasenas y emision de JWT propio de sesion.

Login por email/password (bcrypt). El flujo OAuth de Google (para Calendar/
Tasks/Gmail) es independiente: no autentica al usuario en este servicio, solo
guarda tokens en GoogleCredential para que tools_service los use en nombre del
usuario ya logueado.
"""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_oauth_state_token(platform: str) -> str:
    """Firma un token de corta duracion que viaja como "state" en el flujo
    OAuth de Google - evita CSRF (que /auth/google/callback solo acepte un
    state que esta misma app emitio) y le dice al callback a donde redirigir
    de vuelta (web vs movil) sin depender de sesion de servidor.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {"platform": platform, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_oauth_state_token(token: str) -> str:
    """Devuelve el platform ("web"/"mobile") o lanza jwt.PyJWTError si el
    state es invalido/expirado/no fue emitido por este servicio."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    return payload["platform"]
