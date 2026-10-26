"""Esquemas Pydantic (request/response) del Tools Service, uno por tool."""

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, model_validator


# --- Calendar ---


# Fechas con zona horaria obligatoria: Calendar rechaza las que no la traen y el
# servidor (UTC) las leeria con otra hora. 422 hace que el modelo reintente con offset.
class FreeSlotsRequest(BaseModel):
    window_start: AwareDatetime
    window_end: AwareDatetime
    duration_minutes: int


class FreeSlot(BaseModel):
    start: datetime
    end: datetime


class EventCreate(BaseModel):
    summary: str
    start: AwareDatetime
    end: AwareDatetime
    description: str = ""
    # Evento recurrente (rutina): se repite cada semana en `weekdays` (MO..SU;
    # vacio = el dia de `start`) hasta `until` inclusive. Pedir uno implica el otro,
    # y Calendar exige la zona IANA para que "a las 8" siga siendo las 8 tras un cambio de horario.
    weekdays: list[Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]] | None = None
    until: date | None = None
    timezone: str | None = None

    @model_validator(mode="after")
    def _recurrence(self):
        if not (self.weekdays or self.until):
            return self
        if not self.until:
            raise ValueError("Un evento recurrente necesita `until` (fecha en que deja de repetirse)")
        if self.until < self.start.date():
            raise ValueError("`until` no puede ser anterior al inicio del evento")
        try:
            ZoneInfo(self.timezone or "")
        except Exception:
            raise ValueError("Un evento recurrente necesita `timezone` IANA valida (ej. America/Mexico_City)")
        return self


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

    start: AwareDatetime
    end: AwareDatetime

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
    event_start: AwareDatetime


class TravelTimeResponse(BaseModel):
    travel_seconds: int
    prepare_by: datetime | None = None


class PlacesSearchRequest(BaseModel):
    query: str
    lat: float | None = None
    lng: float | None = None
    # Hora a la que el usuario pretende llegar; con offset para compararla con el horario del lugar.
    at: AwareDatetime | None = None


# --- Gmail ---


class RecentEmailsRequest(BaseModel):
    max_results: int = 10


# --- Device (alarmas / DND, ver app/tools/device_tool.py) ---


class SetAlarmRequest(BaseModel):
    time: datetime
    label: str = ""


class SetFocusModeRequest(BaseModel):
    enabled: bool
