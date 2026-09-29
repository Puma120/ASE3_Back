"""Estado compartido del grafo LangGraph.

Un solo turno de conversacion: mensajes (historial corto + turno actual),
contexto RAG recuperado de Qdrant, resultado de la tool invocada (si el LLM
decidio llamar una) y el texto final de respuesta.
"""

from typing import Any, TypedDict
from uuid import UUID


class AgentState(TypedDict, total=False):
    user_id: UUID
    bearer_token: str  # reenviado a tools_service en call_tool
    messages: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": str}, ...]
    rag_context: list[str]
    tool_call: dict[str, Any] | None  # {"name": str, "arguments": dict} decidido por el LLM
    tool_result: Any | None
    ai_message: Any | None  # AIMessage con tool_calls previo a ToolMessage para Gemini
    response: str
