"""Transiciones condicionales entre nodos del grafo."""

from app.graph.state import AgentState


def should_call_tool(state: AgentState) -> str:
    """Tras call_llm: si el LLM pidio una tool, ejecutarla; si no, ya hay
    respuesta final, pasar a generar la sugerencia proactiva."""
    return "call_tool" if state.get("tool_call") else "generate_proactive_suggestion"
