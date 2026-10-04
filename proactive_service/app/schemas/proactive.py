from datetime import datetime

from pydantic import BaseModel, Field


class DeviceRegister(BaseModel):
    token: str = Field(min_length=10, max_length=4096)
    platform: str = Field(default="android", pattern="^(android|ios|web)$")


class DeviceUnregister(BaseModel):
    token: str


class LocationUpdate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy: float | None = None


class NotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    read: bool
    created_at: datetime
    data: dict = {}


class ReadRequest(BaseModel):
    """ids vacio/omitido = marcar todas como leidas."""

    ids: list[str] | None = None


class ReminderCreate(BaseModel):
    title: str = Field(default="Recordatorio", max_length=120)
    message: str = Field(min_length=1, max_length=500)
    fire_at: datetime


class ReminderOut(BaseModel):
    id: str
    title: str
    message: str
    fire_at: datetime
    status: str
