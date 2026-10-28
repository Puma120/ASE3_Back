"""Horas de vigilia del usuario: recorta los huecos libres para que no se
ofrezcan de madrugada. La hora de despertar y dormir (entre semana y fin de
semana) la guarda el agente en `user_profile.schedule` durante la configuracion
inicial; sin ese dato se usa un horario diurno por defecto."""

import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.db.mongo import user_profile

DEFAULT_WAKE, DEFAULT_SLEEP = "07:00", "23:00"


async def load_schedule(user_id: uuid.UUID) -> dict:
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    return doc.get("schedule") or {}


def _hm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _awake_window(day: date, schedule: dict, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Despierto de `day` (hora de despertar) hasta que duerme; si duerme pasada
    la medianoche, la ventana termina al dia siguiente."""
    kind = "weekend" if day.weekday() >= 5 else "weekday"
    wake = _hm(schedule.get(f"wake_{kind}") or DEFAULT_WAKE)
    sleep = _hm(schedule.get(f"sleep_{kind}") or DEFAULT_SLEEP)
    start = datetime.combine(day, wake, tzinfo=tz)
    end = datetime.combine(day, sleep, tzinfo=tz)
    if end <= start:
        end += timedelta(days=1)
    return start, end


def clip_to_waking_hours(
    slots: list[tuple[datetime, datetime]],
    schedule: dict,
    tz_name: str | None,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Interseca los huecos con las horas despierto; descarta los que quedan
    mas cortos que `duration_minutes`. Sin zona horaria conocida no recorta."""
    tz_name = schedule.get("timezone") or tz_name
    if not tz_name or not slots:
        return slots
    tz = ZoneInfo(tz_name)
    first = min(s for s, _ in slots).astimezone(tz).date() - timedelta(days=1)
    last = max(e for _, e in slots).astimezone(tz).date()
    windows = [_awake_window(first + timedelta(days=n), schedule, tz) for n in range((last - first).days + 1)]

    minimum = timedelta(minutes=duration_minutes)
    clipped = []
    for start, end in slots:
        for w_start, w_end in windows:
            lo, hi = max(start, w_start), min(end, w_end)
            if hi - lo >= minimum:
                clipped.append((lo, hi))
    return sorted(clipped)


START_LEAD_MINUTES = 10  # margen para que el usuario toque el hueco y el agente lo agende sin que ya haya pasado


def earliest_start(now: datetime, window_start: datetime) -> datetime:
    """Primer instante ofrecible: `now` + margen, redondeado hacia arriba a 5 min."""
    lead = now.replace(second=0, microsecond=0) + timedelta(minutes=START_LEAD_MINUTES)
    lead += timedelta(minutes=-lead.minute % 5)
    if lead < now + timedelta(minutes=START_LEAD_MINUTES):
        lead += timedelta(minutes=5)
    return max(window_start, lead)
