"""Dependencia FastAPI para identificar al usuario que conversa con el agente.

Mismo patron que auth_service/tools_service: decodifica localmente el JWT de
sesion (JWT_SECRET_KEY compartido), sin llamar a auth_service por red.
"""

import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings


def _decode_user_id(request: Request) -> uuid.UUID:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = auth_header.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token",
        ) from exc


async def get_current_user_id(
    user_id: uuid.UUID = Depends(_decode_user_id),
) -> uuid.UUID:
    return user_id
