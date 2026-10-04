"""Esquemas Pydantic (request/response) del Tools Service, uno por tool."""

from datetime import datetime

from pydantic import BaseModel


# --- Calendar ---


class FreeSlotsRequest(BaseModel):
    window_start: datetime
    window_end: datetime
    duration_minutes: int


class FreeSlot(BaseModel):
    start: datetime
    end: datetime


class EventCreate(BaseModel):
    summary: str
    start: datetime
    end: datetime
    description: str = ""


class EventSummary(BaseModel):
    id: str
    summary: str
    start: str
    end: str
    all_day: bool = False
    location: str | None = None


# --- Tasks ---


class TaskSummary(BaseModel):
    id: str
    title: str
    notes: str = ""
    due: str | None = None


class TaskCreate(BaseModel):
    title: str
    notes: str = ""


class SubtasksCreate(BaseModel):
    parent_title: str
    subtasks: list[str]


# --- Maps ---


class TravelTimeRequest(BaseModel):
    origin: str
    destination: str
    event_start: datetime


class TravelTimeResponse(BaseModel):
    travel_seconds: int
    prepare_by: datetime | None = None


# --- Gmail ---


class RecentEmailsRequest(BaseModel):
    max_results: int = 10


# --- Device (alarmas / DND, ver app/tools/device_tool.py) ---


class SetAlarmRequest(BaseModel):
    time: datetime
    label: str = ""


class SetFocusModeRequest(BaseModel):
    enabled: bool
