"""Esquemas Pydantic (request/response) del Agent Service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    message: str


class DeviceCommand(BaseModel):
    """Comando para que el cliente lo ejecute en el dispositivo (alarma, focus)."""

    command: str
    payload: dict = {}


class ChatMessageResponse(BaseModel):
    response: str
    device_commands: list[DeviceCommand] = []


class HistoryMessage(BaseModel):
    """Mensaje ya guardado, para que el cliente muestre la conversacion al volver."""

    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SuggestionResponse(BaseModel):
    suggestion: str | None = None
