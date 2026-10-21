"""Tool: calculo de tiempo de traslado y notificacion de hora de salida
(combate time blindness).

Envuelve app/integrations/maps_client.py. No requiere OAuth por usuario
(Maps usa API key de app), asi que no toma `db`/`user_id` como los demas.
"""

from datetime import datetime, timedelta, timezone

from app.integrations import maps_client


async def get_prepare_by_time(
    origin: str,
    destination: str,
    event_start: datetime,
) -> tuple[timedelta, datetime]:
    """Devuelve (tiempo_de_traslado, hora_a_la_que_debe_empezar_a_prepararse)
    para llegar a tiempo a event_start."""
    travel_time = await maps_client.get_travel_time(origin, destination, event_start)
    prepare_by = event_start - travel_time
    return travel_time, prepare_by


def is_open_at(periods: list[dict], local: datetime) -> bool | None:
    """True/False si el lugar esta abierto en `local` (hora local del lugar),
    segun los periodos de Places (day 0 = domingo); None si no hay datos."""
    if not periods:
        return None
    week = 7 * 1440
    now = ((local.weekday() + 1) % 7) * 1440 + local.hour * 60 + local.minute
    for p in periods:
        opens = p.get("open") or {}
        if "close" not in p:
            return True  # sin cierre: abierto 24 horas
        closes = p["close"]
        start = opens.get("day", 0) * 1440 + opens.get("hour", 0) * 60 + opens.get("minute", 0)
        end = closes.get("day", 0) * 1440 + closes.get("hour", 0) * 60 + closes.get("minute", 0)
        if end <= start:
            end += week  # cruza el fin de semana
        if start <= now < end or start <= now + week < end:
            return True
    return False


def _summarize_place(place: dict, at: datetime | None) -> dict:
    hours = place.get("regularOpeningHours") or {}
    summary = {
        "name": (place.get("displayName") or {}).get("text"),
        "address": place.get("formattedAddress"),
        "lat": (place.get("location") or {}).get("latitude"),
        "lng": (place.get("location") or {}).get("longitude"),
        "business_status": place.get("businessStatus"),
        "open_now": (place.get("currentOpeningHours") or {}).get("openNow"),
        "weekly_hours": hours.get("weekdayDescriptions"),
    }
    offset = place.get("utcOffsetMinutes")
    if at is not None:
        # None = Google no publica horario de este lugar: no se puede afirmar nada.
        summary["open_at_requested_time"] = (
            is_open_at(hours.get("periods", []), at.astimezone(timezone(timedelta(minutes=offset))))
            if offset is not None
            else None
        )
    return summary


async def find_places(
    query: str,
    lat: float | None = None,
    lng: float | None = None,
    at: datetime | None = None,
) -> list[dict]:
    """Lugares reales cercanos con direccion y horario; si se pasa `at`, indica
    si cada uno estara abierto a esa hora."""
    places = await maps_client.search_places(query, lat, lng)
    return [_summarize_place(p, at) for p in places]
