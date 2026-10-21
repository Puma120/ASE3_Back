"""Tool: tareas contra calendario y subdivision de tareas grandes en subtareas.

Toda tarea nace con inicio y fin: se crea en Google Tasks (con el fin como
fecha limite), se bloquea el rango en Google Calendar y se registra en
`scheduled_tasks` para que el motor proactivo avise si vence sin completarse.
Envuelve app/integrations/tasks_client.py con la escritura del activity_log
correspondiente (Cap. 3 del PDF: paralisis por analisis en TDAH).
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from googleapiclient.errors import HttpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mongo import activity_logs, scheduled_tasks
from app.integrations import calendar_client, tasks_client
from app.integrations.google_auth import get_user_credentials
from app.models.activity_log import build_activity_log

log = logging.getLogger("tools.tasks")


def _window_note(start: datetime, end: datetime) -> str:
    # Google Tasks no conserva la hora: queda legible en las notas.
    if start.date() == end.date():
        return f"Inicio: {start:%H:%M} - Fin: {end:%H:%M}"
    return f"Inicio: {start:%d/%m %H:%M} - Fin: {end:%d/%m %H:%M}"


def _with_note(notes: str, start: datetime, end: datetime) -> str:
    note = _window_note(start, end)
    return f"{notes}\n{note}" if notes else note


def _utc_iso(value: datetime) -> str:
    return value.replace(tzinfo=timezone.utc).isoformat()


async def _track(
    user_id: uuid.UUID, task_id: str, event_id: str, title: str, start: datetime, end: datetime
) -> None:
    await scheduled_tasks.update_one(
        {"user_id": str(user_id), "task_id": task_id},
        {
            "$set": {
                "event_id": event_id,
                "title": title,
                "start": start.astimezone(timezone.utc),
                "end": end.astimezone(timezone.utc),
                "status": "active",
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


async def _schedule(
    credentials, user_id: uuid.UUID, task: dict, title: str, start: datetime, end: datetime
) -> dict:
    """Bloquea el rango en el calendario y registra la tarea para vigilar su vencimiento."""
    event = await asyncio.to_thread(calendar_client.create_event, credentials, f"Tarea: {title}", start, end, "Creado por Oportuno")
    await _track(user_id, task["id"], event["id"], title, start, end)
    return {**task, "event_id": event["id"], "start": start.isoformat(), "end": end.isoformat()}


async def create_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    notes: str = "",
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    if start is None or end is None:
        raise ValueError("Toda tarea necesita inicio y fin")
    credentials = await get_user_credentials(db, user_id)
    task = await asyncio.to_thread(tasks_client.create_task, credentials, title, _with_note(notes, start, end), end)
    result = await _schedule(credentials, user_id, task, title, start, end)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id),
            "task_created",
            {"title": title, "start": start.isoformat(), "end": end.isoformat()},
        )
    )
    return result


async def create_subtasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    parent_title: str,
    subtasks: list[str],
    start: datetime,
    end: datetime,
) -> list[dict]:
    """La tarea padre lleva la ventana de calendario; las subtareas cuelgan de ella."""
    credentials = await get_user_credentials(db, user_id)
    created = await asyncio.to_thread(tasks_client.create_subtasks, credentials, parent_title, subtasks)
    await asyncio.to_thread(tasks_client.set_due, credentials, created[0]["id"], end, _window_note(start, end))
    created[0] = await _schedule(credentials, user_id, created[0], parent_title, start, end)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id),
            "task_created",
            {
                "parent_title": parent_title,
                "subtasks": subtasks,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
    )
    return created


async def list_pending_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    credentials = await get_user_credentials(db, user_id)
    tasks = await asyncio.to_thread(tasks_client.list_pending_tasks, credentials)
    docs = {
        d["task_id"]: d
        async for d in scheduled_tasks.find({"user_id": str(user_id), "status": "active"})
    }
    for t in tasks:
        if doc := docs.get(t["id"]):
            t["start"] = _utc_iso(doc["start"])
            t["end"] = _utc_iso(doc["end"])
    return tasks


async def complete_task(db: AsyncSession, user_id: uuid.UUID, task_id: str) -> dict:
    credentials = await get_user_credentials(db, user_id)
    task = await asyncio.to_thread(tasks_client.complete_task, credentials, task_id)
    await scheduled_tasks.update_one(
        {"user_id": str(user_id), "task_id": task_id}, {"$set": {"status": "done"}}
    )
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
    task = await asyncio.to_thread(tasks_client.reopen_task, credentials, task_id)
    await scheduled_tasks.update_one(
        {"user_id": str(user_id), "task_id": task_id, "status": "done"}, {"$set": {"status": "active"}}
    )
    await activity_logs.find_one_and_delete(
        {"user_id": str(user_id), "kind": "task_completed", "payload.task_id": task_id},
        sort=[("created_at", -1)],
    )
    return task


async def reschedule_task(
    db: AsyncSession, user_id: uuid.UUID, task_id: str, start: datetime, end: datetime
) -> dict:
    """Mueve la tarea y su evento de calendario a una nueva ventana y la reactiva."""
    credentials = await get_user_credentials(db, user_id)
    task = await asyncio.to_thread(tasks_client.get_task, credentials, task_id)
    title = task.get("title", "")
    doc = await scheduled_tasks.find_one({"user_id": str(user_id), "task_id": task_id})
    # Quita la linea de ventana anterior de las notas para no acumularlas.
    kept = [ln for ln in (task.get("notes") or "").splitlines() if not ln.startswith("Inicio: ")]
    await asyncio.to_thread(tasks_client.set_due, credentials, task_id, end, _with_note("\n".join(kept), start, end))
    event_id = doc["event_id"] if doc else None
    if event_id:
        try:
            await asyncio.to_thread(calendar_client.move_event, credentials, event_id, start, end)
        except HttpError as exc:
            if exc.resp.status not in (404, 410):
                raise
            event_id = None  # el usuario borro el evento: se crea de nuevo
    if not event_id:
        created = await asyncio.to_thread(
            calendar_client.create_event, credentials, f"Tarea: {title}", start, end, "Creado por Oportuno"
        )
        event_id = created["id"]
    await _track(user_id, task_id, event_id, title, start, end)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id),
            "task_rescheduled",
            {"task_id": task_id, "title": title, "start": start.isoformat(), "end": end.isoformat()},
        )
    )
    return {"id": task_id, "title": title, "start": start.isoformat(), "end": end.isoformat()}


async def overdue_tasks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Tareas con fin vencido que siguen sin completarse (insumo del aviso de reagendar).
    Las completadas o borradas en Google se cierran aqui para no revisarlas otra vez."""
    now = datetime.now(timezone.utc)
    docs = [
        d
        async for d in scheduled_tasks.find(
            {"user_id": str(user_id), "status": "active", "end": {"$lte": now}}
        ).limit(20)
    ]
    if not docs:
        return []
    credentials = await get_user_credentials(db, user_id)
    overdue = []
    for doc in docs:
        try:
            task = await asyncio.to_thread(tasks_client.get_task, credentials, doc["task_id"])
        except HttpError as exc:
            if exc.resp.status in (404, 410):
                await scheduled_tasks.update_one({"_id": doc["_id"]}, {"$set": {"status": "gone"}})
                continue
            # Un fallo puntual de Google (429, 5xx) no debe tumbar el resto ni el tick.
            log.warning("no se pudo revisar la tarea %s: %s", doc["task_id"], exc)
            continue
        if task.get("status") == "completed" or task.get("deleted"):
            await scheduled_tasks.update_one({"_id": doc["_id"]}, {"$set": {"status": "done"}})
            continue
        overdue.append(
            {
                "task_id": doc["task_id"],
                "title": doc["title"],
                "start": _utc_iso(doc["start"]),
                "end": _utc_iso(doc["end"]),
            }
        )
    return overdue
