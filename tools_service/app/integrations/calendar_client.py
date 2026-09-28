"""Cliente de bajo nivel para Google Calendar API.

Usado por app/tools/calendar_tool.py para agendar eventos proactivamente en
espacios libres del calendario del usuario (Objetivo 4 del PDF: sugerencias
proactivas de organizacion).
"""

from datetime import datetime, timedelta

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


def create_event(
    credentials: Credentials,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
) -> dict:
    service = _service(credentials)
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    return service.events().insert(calendarId="primary", body=event).execute()
