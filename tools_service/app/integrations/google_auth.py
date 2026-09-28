"""Construye credenciales de google-auth a partir del GoogleCredential
guardado por auth_service, para que los 4 integrations/*_client.py puedan
llamar las APIs de Google en nombre del usuario.
"""

import uuid

from fastapi import HTTPException, status
from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.google_credential import GoogleCredential


async def get_user_credentials(db: AsyncSession, user_id: uuid.UUID) -> Credentials:
    row = await db.scalar(
        select(GoogleCredential).where(GoogleCredential.user_id == user_id)
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail=(
                "El usuario no ha conectado su cuenta de Google todavia "
                "(auth_service /auth/google)."
            ),
        )
    return Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=row.scopes.split(" "),
    )
