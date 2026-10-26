"""Cliente de bajo nivel para Google Calendar API.

Usado por app/tools/calendar_tool.py para agendar eventos proactivamente en
espacios libres del calendario del usuario (Objetivo 4 del PDF: sugerencias
proactivas de organizacion).
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def _service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def find_free_slots(
    credentials: Credentials,
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Consulta freebusy en [window_start, window_end] y devuelve los huecos
    libres de al menos `duration_minutes`, mas antiguo primero."""
    service = _service(credentials)
    body = {
        "timeMin": window_start.isoformat(),
        "timeMax": window_end.isoformat(),
        "items": [{"id": "primary"}],
    }
    busy = service.freebusy().query(body=body).execute()
    busy_slots = busy["calendars"]["primary"]["busy"]

    free_slots: list[tuple[datetime, datetime]] = []
    cursor = window_start
    for slot in busy_slots:
        busy_start = datetime.fromisoformat(slot["start"])
        busy_end = datetime.fromisoformat(slot["end"])
        if busy_start - cursor >= timedelta(minutes=duration_minutes):
            free_slots.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if window_end - cursor >= timedelta(minutes=duration_minutes):
        free_slots.append((cursor, window_end))
    return free_slots


_WEEKDAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def build_recurring(
    start: datetime, end: datetime, weekdays: list[str], until: date, tz_name: str
) -> tuple[datetime, datetime, list[str]]:
    """Primera ocurrencia (en la zona del usuario) y RRULE semanal hasta `until`.
    Calendar cuenta DTSTART aunque no caiga en BYDAY, asi que se adelanta a un dia que si."""
    tz = ZoneInfo(tz_name)
    local_start, local_end = start.astimezone(tz), end.astimezone(tz)
    days = weekdays or [_WEEKDAYS[local_start.weekday()]]
    shift = next(n for n in range(7) if _WEEKDAYS[(local_start.weekday() + n) % 7] in days)
    local_start, local_end = local_start + timedelta(days=shift), local_end + timedelta(days=shift)
    # UNTIL de un evento con hora va en UTC: fin del ultimo dia, en la zona del usuario.
    last_instant = datetime.combine(until, time(23, 59, 59), tzinfo=tz).astimezone(timezone.utc)
    rule = f"RRULE:FREQ=WEEKLY;BYDAY={','.join(days)};UNTIL={last_instant:%Y%m%dT%H%M%SZ}"
    return local_start, local_end, [rule]


def create_event(
    credentials: Credentials,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
    weekdays: list[str] | None = None,
    until: date | None = None,
    tz_name: str | None = None,
) -> dict:
    service = _service(credentials)
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    if until:
        start, end, event["recurrence"] = build_recurring(start, end, weekdays or [], until, tz_name)
        event["start"] = {"dateTime": start.isoformat(), "timeZone": tz_name}
        event["end"] = {"dateTime": end.isoformat(), "timeZone": tz_name}
    return service.events().insert(calendarId="primary", body=event).execute()


def move_event(credentials: Credentials, event_id: str, start: datetime, end: datetime) -> dict:
    body = {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
    return (
        _service(credentials).events().patch(calendarId="primary", eventId=event_id, body=body).execute()
    )


def list_events(credentials: Credentials, window_start: datetime, window_end: datetime) -> list[dict]:
    """Eventos del calendario principal en [window_start, window_end], por hora de inicio."""
    service = _service(credentials)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=window_start.isoformat(),
            timeMax=window_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    return result.get("items", [])
