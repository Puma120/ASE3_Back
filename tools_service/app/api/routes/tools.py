"""Endpoints HTTP que exponen las tools al Microservicio del Agente.

Un endpoint por tool (no uno generico): cada tool tiene su propio contrato
de request/payload (ver app/schemas/tools.py), asi que un endpoint generico
solo moveria el dispatch de FastAPI a codigo propio sin ganar nada.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user_id
from app.db.postgres import get_db
from app.schemas.tools import (
    EventCreate,
    EventSummary,
    FreeSlot,
    FreeSlotsRequest,
    RecentEmailsRequest,
    SetAlarmRequest,
    SetFocusModeRequest,
    SubtasksCreate,
    TaskCreate,
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
        db, user_id, body.window_start, body.window_end, body.duration_minutes
    )
    return [FreeSlot(start=start, end=end) for start, end in slots]


@router.get("/calendar/events")
async def list_calendar_events(
    window_start: datetime,
    window_end: datetime,
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
        db, user_id, body.summary, body.start, body.end, body.description
    )


# --- Tasks ---


@router.post("/tasks")
async def create_task(
    body: TaskCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.create_task(db, user_id, body.title, body.notes)


@router.post("/tasks/subtasks")
async def create_subtasks(
    body: SubtasksCreate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await tasks_tool.create_subtasks(db, user_id, body.parent_title, body.subtasks)


@router.get("/tasks", response_model=list[TaskSummary])
async def list_tasks(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    tasks = await tasks_tool.list_pending_tasks(db, user_id)
    return [
        TaskSummary(id=t["id"], title=t.get("title", ""), notes=t.get("notes", ""), due=t.get("due"))
        for t in tasks
        if t.get("title")
    ]


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    task = await tasks_tool.complete_task(db, user_id, task_id)
    return {"id": task["id"], "status": task["status"]}


# --- Routines ---


@router.get("/routines/summary")
async def routines_summary(user_id: uuid.UUID = Depends(get_current_user_id)):
    return await routines_tool.routines_summary(user_id)


# --- Maps ---


@router.post("/maps/travel-time", response_model=TravelTimeResponse)
async def travel_time(body: TravelTimeRequest):
    travel, prepare_by = await maps_tool.get_prepare_by_time(
        body.origin, body.destination, body.event_start
    )
    return TravelTimeResponse(
        travel_seconds=int(travel.total_seconds()),
        prepare_by=prepare_by,
    )


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
