"""Envio de push via Firebase Cloud Messaging (HTTP v1).

Credenciales: JSON de cuenta de servicio en FCM_SERVICE_ACCOUNT_JSON (el
contenido, no una ruta) + FCM_PROJECT_ID. Sin ellas `send` devuelve
"disabled" y el resto del sistema sigue funcionando (bandeja en BD).
"""

import asyncio
import json
import logging

import httpx
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import service_account

from app.core.config import settings

log = logging.getLogger("proactive.fcm")

_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_credentials: service_account.Credentials | None = None


def is_configured() -> bool:
    return bool(settings.fcm_project_id and settings.fcm_service_account_json)


def _access_token() -> str:
    global _credentials
    if _credentials is None:
        info = json.loads(settings.fcm_service_account_json)
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
    if not _credentials.valid:
        _credentials.refresh(GoogleRequest())
    return _credentials.token


async def send(token: str, title: str, body: str, data: dict[str, str] | None = None) -> str:
    """Devuelve "sent", "invalid_token" (borrar el dispositivo), "disabled" o "error"."""
    if not is_configured():
        return "disabled"
    try:
        access_token = await asyncio.to_thread(_access_token)
        message = {
            "message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": {k: str(v) for k, v in (data or {}).items()},
                "android": {"priority": "high"},
            }
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send",
                json=message,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code == 200:
            return "sent"
        if response.status_code in (400, 404) and "UNREGISTERED" in response.text:
            return "invalid_token"
        log.warning("FCM %s: %s", response.status_code, response.text[:300])
        return "error"
    except Exception:
        log.exception("FCM send fallo")
        return "error"
