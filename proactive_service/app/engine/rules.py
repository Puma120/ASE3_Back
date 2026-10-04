"""Reglas puras del motor proactivo (sin I/O, faciles de probar).

Cada regla recibe datos ya cargados y devuelve `Alert`s; el tick decide a
quien evaluar y `notify.deliver` hace el dedupe por `dedupe_key`.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Pasada esta ventana desde la hora de salida el aviso deja de ser "sal ya" y
# pasa a "vas tarde".
LEAVE_WINDOW = timedelta(minutes=10)
SOON_LEAD = timedelta(minutes=10)


@dataclass
class Alert:
    kind: str
    title: str
    body: str
    dedupe_key: str
    data: dict = field(default_factory=dict)


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hhmm(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")


def _minutes(seconds: float) -> int:
    return max(1, math.ceil(seconds / 60))


def departure_alerts(
    event: dict,
    now: datetime,
    travel_seconds: int,
    tz: ZoneInfo,
    prepare_lead: timedelta,
    buffer: timedelta,
) -> list[Alert]:
    """Avisos de "prepárate / sal ya / vas tarde" para un evento con lugar."""
    start = parse_dt(event["start"])
    if now >= start:
        return []

    travel = timedelta(seconds=travel_seconds)
    if travel < timedelta(minutes=2):
        return []  # ya esta en el lugar

    leave_at = start - travel - buffer
    prepare_at = leave_at - prepare_lead
    place = event.get("location") or "el lugar"
    name = event.get("summary", "tu evento")
    travel_min = _minutes(travel_seconds)
    base = f"departure:{event['id']}:{event['start']}"
    data = {"event_id": event["id"], "leave_at": leave_at.isoformat()}

    if prepare_at <= now < leave_at:
        return [
            Alert(
                "prepare",
                "Prepárate para salir",
                f"Para «{name}» a las {_hhmm(start, tz)} en {place}, la ruta marca "
                f"{travel_min} min. Prepárate y sal a las {_hhmm(leave_at, tz)}.",
                f"{base}:prepare",
                data,
            )
        ]
    if leave_at <= now < leave_at + LEAVE_WINDOW:
        return [
            Alert(
                "leave",
                "Ya deberías salir",
                f"Para llegar a {place} a las {_hhmm(start, tz)} el trayecto son {travel_min} min. "
                "Sal ahora.",
                f"{base}:leave",
                data,
            )
        ]
    if now >= leave_at + LEAVE_WINDOW:
        remaining = (start - now).total_seconds()
        if travel_seconds <= remaining:
            body = (
                f"Se hace tarde para «{name}». Si sales ya llegas en {travel_min} min "
                f"y te quedan {_minutes(remaining)}."
            )
        else:
            late = _minutes(travel_seconds - remaining)
            body = (
                f"Si sales ahora llegas a {place} unos {late} min tarde "
                f"(trayecto {travel_min} min, faltan {_minutes(remaining)})."
            )
        return [Alert("late", "Vas tarde", body, f"{base}:late", data)]
    return []


def soon_alert(event: dict, now: datetime, tz: ZoneInfo) -> Alert | None:
    """Aviso corto de "en 10 min" para eventos sin ruta calculable."""
    start = parse_dt(event["start"])
    if not (start - SOON_LEAD <= now < start):
        return None
    mins = _minutes((start - now).total_seconds())
    return Alert(
        "soon",
        "Tu evento está por empezar",
        f"«{event.get('summary', 'Evento')}» empieza en {mins} min ({_hhmm(start, tz)}).",
        f"soon:{event['id']}:{event['start']}",
        {"event_id": event["id"]},
    )


def briefing_alert(
    events: list[dict],
    tasks: list[dict],
    now: datetime,
    tz: ZoneInfo,
    work_start_hour: int,
) -> Alert | None:
    """Resumen del dia, una vez por fecha local, a partir de la hora de inicio de jornada."""
    local = now.astimezone(tz)
    if not (work_start_hour <= local.hour < work_start_hour + 3):
        return None
    timed = [e for e in events if not e.get("all_day")]
    if not timed and not tasks:
        return None

    parts = []
    if timed:
        first = timed[0]
        parts.append(
            f"{len(timed)} evento{'s' if len(timed) != 1 else ''} "
            f"(el primero: «{first['summary']}» a las {_hhmm(parse_dt(first['start']), tz)})"
        )
    if tasks:
        parts.append(f"{len(tasks)} tarea{'s' if len(tasks) != 1 else ''} pendiente{'s' if len(tasks) != 1 else ''}")
    return Alert(
        "briefing",
        "Tu día de hoy",
        "Hoy tienes " + " y ".join(parts) + ".",
        f"briefing:{local.date().isoformat()}",
    )
