"""Esquemas Pydantic (request/response) del Agent Service."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    # Tope por mensaje: cada uno entra al prompt del LLM y al RAG.
    message: str = Field(min_length=1, max_length=4000)
    # Zona IANA del dispositivo (ej. America/Mexico_City); manda sobre la de Ajustes.
    timezone: str | None = None
    # Posicion GPS del telefono en este mensaje (solo si el usuario activo
    # "Usar mi ubicacion en el chat"); manda sobre la ultima guardada.
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


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
