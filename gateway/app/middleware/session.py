"""Validacion de sesion (JWT) antes de enrutar hacia los microservicios internos.

El JWT se decodifica localmente con el JWT_SECRET_KEY compartido (sin llamar a
auth_service en cada request): mas rapido, a costa de compartir el secreto de
firma entre los servicios.
"""

from fastapi import Request, HTTPException, status
import jwt

from app.core.config import settings


def get_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    return auth_header.removeprefix("Bearer ")


def validate_session(request: Request) -> dict:
    """Decodifica y valida el JWT de sesion. Lanza 401 si es invalido/expirado."""
    token = get_bearer_token(request)
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from exc
    return payload
