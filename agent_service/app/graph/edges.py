"""Transiciones condicionales entre nodos del grafo."""

from app.graph.state import AgentState


def should_call_tool(state: AgentState) -> str:
    """Tras call_llm: si el LLM pidio tools, ejecutarlas; si no, ya hay
    respuesta final, pasar a generar la sugerencia proactiva."""
    return "call_tool" if state.get("pending_calls") else "generate_proactive_suggestion"
