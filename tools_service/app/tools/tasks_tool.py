"""Tool: subdivision de tareas grandes/abrumadoras en subtareas accionables.

Envuelve app/integrations/tasks_client.py con la escritura del activity_log
correspondiente (Cap. 3 del PDF: paralisis por analisis en TDAH).
"""

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mongo import activity_logs
from app.integrations import tasks_client
from app.integrations.google_auth import get_user_credentials
from app.models.activity_log import build_activity_log


async def create_task(
    db: AsyncSession, user_id: uuid.UUID, title: str, notes: str = "", due: datetime | None = None
) -> dict:
    if due is not None:
        # La API no conserva la hora: queda legible en las notas.
        hora = f"Hora: {due:%H:%M}"
        notes = f"{notes}\n{hora}" if notes else hora
    credentials = await get_user_credentials(db, user_id)
    task = tasks_client.create_task(credentials, title, notes, due)
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


async def list_pending_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    credentials = await get_user_credentials(db, user_id)
    return tasks_client.list_pending_tasks(credentials)


async def complete_task(db: AsyncSession, user_id: uuid.UUID, task_id: str) -> dict:
    credentials = await get_user_credentials(db, user_id)
    task = tasks_client.complete_task(credentials, task_id)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id), "task_completed", {"task_id": task_id, "title": task.get("title", "")}
        )
    )
    return task


async def reopen_task(db: AsyncSession, user_id: uuid.UUID, task_id: str) -> dict:
    """"Deshacer" del front: reabre la tarea y borra su registro de completada
    para que la racha y el resumen semanal no cuenten un error de toque."""
    credentials = await get_user_credentials(db, user_id)
    task = tasks_client.reopen_task(credentials, task_id)
    await activity_logs.find_one_and_delete(
        {"user_id": str(user_id), "kind": "task_completed", "payload.task_id": task_id},
        sort=[("created_at", -1)],
    )
    return task
