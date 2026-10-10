"""Contexto del usuario que se inyecta al prompt: quien es, que hora es para
el, donde esta. Solo datos de perfil/ajustes/ubicacion: nunca credenciales ni
nada de auth (el agente ni siquiera tiene forma de pedirlos)."""

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.clients.tools_client import fetch_json

_DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


async def build_user_context(bearer_token: str, device_tz: str | None = None) -> str:
    profile, settings, location = await asyncio.gather(
        fetch_json("auth", "/auth/users/me", bearer_token),
        fetch_json("auth", "/auth/users/me/settings", bearer_token),
        fetch_json("proactive", "/proactive/location", bearer_token),
    )
    settings = settings or {}
    tz = _zone(device_tz) or _zone(settings.get("timezone")) or ZoneInfo("UTC")
    now = datetime.now(timezone.utc).astimezone(tz)

    lines = [
        f"Fecha y hora actuales del usuario: {_DAYS[now.weekday()]} {now.isoformat(timespec='minutes')} "
        f"(zona horaria {tz.key}). Usa SIEMPRE esta zona para fechas relativas como "
        "'manana' o 'a las 5', y manda los datetime ISO con su offset.",
    ]
    if profile and profile.get("full_name"):
        lines.append(f"Nombre del usuario: {profile['full_name']}.")
    if settings:
        lines.append(
            f"Jornada: {settings.get('work_start_hour', 9)}:00 a {settings.get('work_end_hour', 18)}:00. "
            "No agendes cosas proactivas fuera de ese horario."
        )
    loc = (location or {}).get("location")
    if loc:
        lines.append(
            f"Ultima ubicacion conocida (lat,lng): {loc['lat']},{loc['lng']} (hace {_age(loc['updated_at'])}). "
            "Usala como origin para calcular traslados."
        )
    else:
        lines.append("Ubicacion actual: desconocida. Si necesitas un origen, preguntalo.")
    return "\n".join(lines)


def _zone(name: str | None) -> ZoneInfo | None:
    """La zona del dispositivo manda sobre la de Ajustes; si es invalida, se ignora."""
    try:
        return ZoneInfo(name) if name else None
    except Exception:
        return None


def _age(iso: str) -> str:
    minutes = int((datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() // 60)
    if minutes < 2:
        return "instantes"
    if minutes < 90:
        return f"{minutes} min"
    return f"{minutes // 60} h"
