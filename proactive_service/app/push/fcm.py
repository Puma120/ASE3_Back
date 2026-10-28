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
        # strict=False: al pegar el JSON en Railway el private_key puede traer saltos de linea reales
        info = json.loads(settings.fcm_service_account_json, strict=False)
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=[_SCOPE])
    if not _credentials.valid:
        _credentials.refresh(GoogleRequest())
    return _credentials.token


# Canales que crea el front (mobile/src/native/push.native.ts). Por defecto
# los avisos no suenan; el usuario elige "Con sonido" en Ajustes.
CHANNEL_SILENT = "avisos_silencio"
CHANNEL_SOUND = "avisos_sonido"


def build_message(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None,
    channel_id: str,
    bubble: bool,
) -> dict:
    payload = {k: str(v) for k, v in (data or {}).items()}
    if bubble:
        # Solo-datos: sin bloque "notification" Android no pinta nada por su
        # cuenta y la app (BubbleMessagingService) arma la burbuja de chat.
        payload.update(
            {
                "bubble": "1",
                "title": title,
                "body": body,
                "sound": "1" if channel_id == CHANNEL_SOUND else "0",
            }
        )
        return {"message": {"token": token, "data": payload, "android": {"priority": "high"}}}
    return {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": payload,
            "android": {"priority": "high", "notification": {"channel_id": channel_id}},
        }
    }


async def send(
    token: str,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
    channel_id: str = CHANNEL_SILENT,
    bubble: bool = False,
) -> str:
    """Devuelve "sent", "invalid_token" (borrar el dispositivo), "disabled" o "error"."""
    return await _post(build_message(token, title, body, data, channel_id, bubble))


def build_focus_message(token: str, enabled: bool) -> dict:
    """Solo-datos y sin notificacion visible: la app (BubbleMessagingService) cambia No molestar."""
    return {"message": {"token": token, "data": {"focus": "on" if enabled else "off"}, "android": {"priority": "high"}}}


async def send_focus(token: str, enabled: bool) -> str:
    return await _post(build_focus_message(token, enabled))


async def _post(message: dict) -> str:
    if not is_configured():
        return "disabled"
    try:
        access_token = await asyncio.to_thread(_access_token)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://fcm.googleapis.com/v1/projects/{settings.fcm_project_id}/messages:send",
                json=message,
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if response.status_code == 200:
            return "sent"
        if response.status_code in (400, 404) and (
            "UNREGISTERED" in response.text or "not a valid FCM registration token" in response.text
        ):
            return "invalid_token"
        log.warning("FCM %s: %s", response.status_code, response.text[:300])
        return "error"
    except Exception:
        log.exception("FCM send fallo")
        return "error"
