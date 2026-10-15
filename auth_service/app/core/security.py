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


def create_email_verification_token(email: str, hashed_password: str, full_name: str) -> str:
    """Token firmado con los datos del registro pendiente: la cuenta no existe
    en la BD hasta que el dueno del correo abre el enlace. Lleva el hash bcrypt
    (nunca la contrasena) y solo viaja al correo que se esta verificando."""
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.email_verification_expire_hours
    )
    payload = {
        "typ": "verify_email",
        "email": email,
        "pwd": hashed_password,
        "name": full_name,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_email_verification_token(token: str) -> dict:
    """Devuelve el payload o lanza jwt.PyJWTError (invalido, expirado, o un JWT
    de otro tipo, p. ej. un token de sesion)."""
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != "verify_email":
        raise jwt.InvalidTokenError("tipo de token incorrecto")
    return payload


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
