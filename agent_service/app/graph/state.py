"""Estado compartido del grafo LangGraph.

Un turno de conversacion: mensajes (historial corto + turno actual), contexto
RAG, contexto del usuario (perfil/hora/ubicacion), la cola de tool_calls
pendientes de la ronda actual y los mensajes de tools ya intercambiados con
el LLM en este turno.
"""

from typing import Any, TypedDict
from uuid import UUID


class AgentState(TypedDict, total=False):
    user_id: UUID
    bearer_token: str  # reenviado a tools_service/proactive_service en call_tool
    messages: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": str}, ...]
    rag_context: list[str]
    user_context: str  # perfil, fecha/hora local, ubicacion; se inyecta en el prompt
    pending_calls: list[dict[str, Any]]  # tool_calls de la ronda actual: {"id","name","arguments"}
    tool_exchange: list[Any]  # AIMessage/ToolMessage ya intercambiados en este turno
    untrusted_seen: bool  # el turno leyo contenido de terceros (correos): sin tools de escritura
    rounds: int
    response: str
    params: dict[str, Any]  # AgentParams del usuario (top-k, temperatura, ventana)
    device_commands: list[dict[str, Any]]  # comandos para el dispositivo (alarma, focus)
