"""Endpoints HTTP que exponen las tools al Microservicio del Agente.

Un endpoint por tool (no uno generico): cada tool tiene su propio contrato
de request/payload (ver app/schemas/tools.py), asi que un endpoint generico
solo moveria el dispatch de FastAPI a codigo propio sin ganar nada.
"""

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user_id
from app.db.postgres import get_db
from app.schemas.tools import (
    EventCreate,
    EventSummary,
    FreeSlot,
    FreeSlotsRequest,
    PlacesSearchRequest,
    RecentEmailsRequest,
    SetAlarmRequest,
    SetFocusModeRequest,
    SubtasksCreate,
    TaskCreate,
    TaskReschedule,
    TaskSummary,
    TravelTimeRequest,
    TravelTimeResponse,
)
from app.tools import (
    calendar_tool,
    device_tool,
    gmail_tool,
    maps_tool,
    routines_tool,
    tasks_tool,
)

router = APIRouter(prefix="/tools", tags=["tools"])


# --- Calendar ---


@router.post("/calendar/free-slots", response_model=list[FreeSlot])
async def free_slots(
    body: FreeSlotsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    slots = await calendar_tool.find_free_slots(
        db, user_id, body.window_start, body.window_end, body.duration_minutes, body.timezone
    )
    return [FreeSlot(start=start, end=end) for start, end in slots]


@router.get("/calendar/events")
async def list_calendar_events(
    window_start: AwareDatetime,
    window_end: AwareDatetime,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    events = await calendar_tool.list_events(db, user_id, window_start, window_end)
    return [
        EventSummary(
            id=e["id"],
            summary=e.get("summary", "(sin titulo)"),
            start=e["start"].get("dateTime") or e["start"].get("date"),
            end=e["end"].get("dateTime") or e["end"].get("date"),
            all_day="date" in e["start"],
            location=e.get("location"),
        )
        for e in events
    ]


@router.post("/calendar/events")
async def create_calendar_event(
    body: EventCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await calendar_tool.create_event(
        db, user_id, body.summary, body.start, body.end, body.description, body.weekdays, body.until, body.timezone
    )


# --- Tasks ---


@router.post("/tasks")
async def create_task(
    body: TaskCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.create_task(
        db, user_id, body.title, body.notes or "", body.start, body.end, body.focus
    )


@router.post("/tasks/subtasks")
async def create_subtasks(
    body: SubtasksCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.create_subtasks(
        db, user_id, body.parent_title, body.subtasks, body.start, body.end, body.focus
    )


@router.get("/tasks", response_model=list[TaskSummary])
async def list_tasks(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tasks = await tasks_tool.list_pending_tasks(db, user_id)
    return [
        TaskSummary(
            id=t["id"],
            title=t.get("title", ""),
            notes=t.get("notes", ""),
            due=t.get("due"),
            start=t.get("start"),
            end=t.get("end"),
        )
        for t in tasks
        if t.get("title")
    ]


@router.get("/tasks/focus-now")
async def focus_now(user_id: uuid.UUID = Depends(get_current_user_id)):
    """Tareas de enfoque cuya ventana esta en curso (insumo de No molestar automatico)."""
    return await tasks_tool.focus_now(user_id)


@router.get("/tasks/overdue")
async def overdue_tasks(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.overdue_tasks(db, user_id)


@router.post("/tasks/{task_id}/reschedule")
async def reschedule_task(
    task_id: str,
    body: TaskReschedule,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.reschedule_task(db, user_id, task_id, body.start, body.end)


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    task = await tasks_tool.complete_task(db, user_id, task_id)
    return {"id": task["id"], "status": task["status"]}


@router.post("/tasks/{task_id}/reopen")
async def reopen_task(
    task_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    task = await tasks_tool.reopen_task(db, user_id, task_id)
    return {"id": task["id"], "status": task["status"]}


# --- Routines ---


@router.get("/routines/summary")
async def routines_summary(user_id: uuid.UUID = Depends(get_current_user_id)):
    return await routines_tool.routines_summary(user_id)


# --- Maps ---


@router.post("/maps/travel-time", response_model=TravelTimeResponse)
async def travel_time(body: TravelTimeRequest):
    try:
        travel, prepare_by = await maps_tool.get_prepare_by_time(
            body.origin, body.destination, body.event_start
        )
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Maps no pudo calcular la ruta: {exc}") from exc
    return TravelTimeResponse(
        travel_seconds=int(travel.total_seconds()),
        prepare_by=prepare_by,
    )


@router.post("/maps/places")
async def search_places(
    body: PlacesSearchRequest, user_id: uuid.UUID = Depends(get_current_user_id)
):
    try:
        places = await maps_tool.find_places(body.query, body.lat, body.lng, body.at)
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo buscar lugares: {exc}") from exc
    return {"places": places}


# --- Gmail ---


@router.post("/gmail/recent-emails")
async def recent_emails(
    body: RecentEmailsRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await gmail_tool.read_recent_emails(db, user_id, body.max_results)


# --- Device (alarmas / DND) ---


@router.post("/device/alarm")
async def set_alarm(
    body: SetAlarmRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await device_tool.set_alarm(user_id, body.time, body.label)


@router.post("/device/focus-mode")
async def set_focus_mode(
    body: SetFocusModeRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    return await device_tool.set_focus_mode(user_id, body.enabled)
