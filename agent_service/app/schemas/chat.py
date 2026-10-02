"""Esquemas Pydantic (request/response) del Agent Service."""

from pydantic import BaseModel


class ChatMessageRequest(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    response: str


class SuggestionResponse(BaseModel):
    suggestion: str | None = None
