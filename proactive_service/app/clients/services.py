"""Cliente HTTP hacia tools_service/auth_service en nombre de un usuario."""

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.security import mint_user_token

log = logging.getLogger("proactive.clients")


class GoogleNotConnected(Exception):
    """tools_service respondio 428: el usuario no ha conectado Google."""


def _headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_user_token(user_id)}"}


async def _get(base: str, path: str, user_id: str, params: dict | None = None) -> Any:
    async with httpx.AsyncClient(base_url=base, timeout=20.0) as client:
        response = await client.get(path, params=params, headers=_headers(user_id))
    if response.status_code == 428:
        raise GoogleNotConnected
    response.raise_for_status()
    return response.json()


async def get_user_settings(user_id: str) -> dict:
    return await _get(settings.auth_service_url, "/auth/users/me/settings", user_id)


async def get_profile(user_id: str) -> dict:
    return await _get(settings.auth_service_url, "/auth/users/me", user_id)


async def list_events(user_id: str, window_start: str, window_end: str) -> list[dict]:
    return await _get(
        settings.tools_service_url,
        "/tools/calendar/events",
        user_id,
        {"window_start": window_start, "window_end": window_end},
    )


async def list_tasks(user_id: str) -> list[dict]:
    return await _get(settings.tools_service_url, "/tools/tasks", user_id)


async def travel_time(user_id: str, origin: str, destination: str, event_start: str) -> int | None:
    """Segundos de traslado, o None si Maps no pudo calcular la ruta."""
    try:
        async with httpx.AsyncClient(base_url=settings.tools_service_url, timeout=20.0) as client:
            response = await client.post(
                "/tools/maps/travel-time",
                json={"origin": origin, "destination": destination, "event_start": event_start},
                headers=_headers(user_id),
            )
        response.raise_for_status()
        return int(response.json()["travel_seconds"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("travel_time fallo (%s -> %s): %s", origin, destination, exc)
        return None
