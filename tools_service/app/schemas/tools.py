"""Esquemas Pydantic (request/response) del Tools Service, uno por tool."""

from datetime import datetime

from pydantic import BaseModel, model_validator


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
    start: str | None = None
    end: str | None = None


class _Window(BaseModel):
    """Toda tarea va contra calendario: inicio y fin obligatorios."""

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _end_after_start(self):
        if self.end <= self.start:
            raise ValueError("end debe ser posterior a start")
        return self


class TaskCreate(_Window):
    title: str
    # El modelo a veces manda notes: null; se acepta y se trata como vacio.
    notes: str | None = ""


class SubtasksCreate(_Window):
    parent_title: str
    subtasks: list[str]


class TaskReschedule(_Window):
    pass


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
