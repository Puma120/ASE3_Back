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
    messages: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": str}, ...]
    rag_context: list[str]
    summary: str  # memoria corta compactada: resumen de lo que ya salio de la ventana
    pending_actions: str  # estado operativo: acciones bloqueadas pendientes de confirmar
    timezone: str  # zona IANA del dispositivo en este turno (opcional)
    location: dict[str, float]  # {"lat","lng"} del GPS del telefono en este turno (opcional)
    onboarding: bool  # configuracion inicial de la rutina: el agente conduce la entrevista
    onboarding_done: bool  # el agente la cerro en este turno (finish_onboarding)
    routine: str  # datos fijos de rutina vigentes (memory/profile.py), formateados
    user_context: str  # perfil, fecha/hora local, ubicacion; se inyecta en el prompt
    pending_calls: list[dict[str, Any]]  # tool_calls de la ronda actual: {"id","name","arguments"}
    tool_exchange: list[Any]  # AIMessage/ToolMessage ya intercambiados en este turno
    untrusted_seen: bool  # el turno leyo contenido de terceros (correos): sin tools de escritura
    rounds: int
    response: str
    params: dict[str, Any]  # AgentParams del usuario (top-k, temperatura, ventana)
    device_commands: list[dict[str, Any]]  # comandos para el dispositivo (alarma, focus)
