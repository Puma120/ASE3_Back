"""Tool: subdivision de tareas grandes/abrumadoras en subtareas accionables.

Envuelve app/integrations/tasks_client.py con la escritura del activity_log
correspondiente (Cap. 3 del PDF: paralisis por analisis en TDAH).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mongo import activity_logs
from app.integrations import tasks_client
from app.integrations.google_auth import get_user_credentials
from app.models.activity_log import build_activity_log


async def create_task(db: AsyncSession, user_id: uuid.UUID, title: str, notes: str = "") -> dict:
    credentials = await get_user_credentials(db, user_id)
    task = tasks_client.create_task(credentials, title, notes)
    await activity_logs.insert_one(
        build_activity_log(str(user_id), "task_created", {"title": title})
    )
    return task


async def create_subtasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    parent_title: str,
    subtasks: list[str],
) -> list[dict]:
    credentials = await get_user_credentials(db, user_id)
    created = tasks_client.create_subtasks(credentials, parent_title, subtasks)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id),
            "task_created",
            {"parent_title": parent_title, "subtasks": subtasks},
        )
    )
    return created
