"""JWT de servicio: el tick corre sin sesion del usuario, asi que emite un
token de vida corta con el JWT_SECRET_KEY compartido para llamar a
tools_service/auth_service en su nombre (mismo contrato que el token de login)."""

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings


def mint_user_token(user_id: str, minutes: int = 5) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
