"""Tool: agendado proactivo de eventos en espacios libres del calendario.

Envuelve app/integrations/calendar_client.py con la escritura del
activity_log correspondiente (Objetivo 4 del PDF).
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mongo import activity_logs
from app.integrations import calendar_client
from app.integrations.google_auth import get_user_credentials
from app.models.activity_log import build_activity_log


async def find_free_slots(
    db: AsyncSession,
    user_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    duration_minutes: int,
) -> list[tuple[datetime, datetime]]:
    credentials = await get_user_credentials(db, user_id)
    return calendar_client.find_free_slots(credentials, window_start, window_end, duration_minutes)


async def create_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    summary: str,
    start: datetime,
    end: datetime,
    description: str = "",
) -> dict:
    credentials = await get_user_credentials(db, user_id)
    event = calendar_client.create_event(credentials, summary, start, end, description)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id),
            "event_scheduled",
            {"summary": summary, "start": start.isoformat(), "end": end.isoformat()},
        )
    )
    return event
