"""Flujo OAuth 2.0 de Google en modo "login": construye la URL de consentimiento,
intercambia el codigo por tokens y obtiene el perfil del usuario (email/nombre).

Se piden a proposito los mismos scopes que tools_service necesita (Calendar/
Tasks/Gmail) ademas de los de identidad (openid/email/profile): asi "Entrar con
Google" deja al usuario logueado Y con su cuenta de Google ya conectada para
las tools en un solo consentimiento, completando el GoogleCredential que
tools_service/app/integrations/google_auth.py espera.
"""

from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = " ".join(
    [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/tasks",
        "https://www.googleapis.com/auth/gmail.readonly",
    ]
)


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    """Intercambia el codigo de autorizacion por access/refresh token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google rechazo el codigo de autorizacion",
        )
    return response.json()


async def fetch_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo obtener el perfil de Google",
        )
    return response.json()
