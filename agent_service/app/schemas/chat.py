"""Esquemas Pydantic (request/response) del Agent Service."""

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


class SuggestionResponse(BaseModel):
    suggestion: str | None = None
