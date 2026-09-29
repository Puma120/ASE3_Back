"""Nodos individuales del grafo del agente.

Flujo: retrieve_context (RAG) -> call_llm (Gemini, con tools bindeadas) ->
[call_tool -> call_llm de nuevo para redactar la respuesta final, si el LLM
pidio una tool] -> generate_proactive_suggestion (Objetivo 4 del PDF).
"""

import json
from collections import Counter
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.clients.tools_client import call_tool as invoke_tool
from app.core.config import settings
from app.db.mongo import activity_logs
from app.graph.state import AgentState
from app.graph.tool_specs import TOOL_SPECS
from app.memory import vector_store

SYSTEM_PROMPT = (
    "Eres un asistente conversacional que ayuda a adultos con TDAH a organizar "
    "sus actividades. Responde de forma breve, concreta y sin ambiguedad "
    "(evita parrafos largos: aumentan la carga cognitiva). Cuando el usuario "
    "necesite agendar algo, crear tareas, saber cuando salir, revisar correo, "
    "o poner una alarma/modo no molestar, usa la tool correspondiente en vez "
    "de solo describir que se podria hacer."
)

_llm = None


def _get_llm():
    """Lazy init: construir ChatGoogleGenerativeAI en el import falla si
    GEMINI_API_KEY esta vacio (pydantic valida el key al crear el objeto),
    lo cual tumbaria el servicio completo antes de tener credenciales reales."""
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            google_api_key=settings.gemini_api_key,
            temperature=settings.llm_temperature,
        ).bind_tools(TOOL_SPECS)
    return _llm


async def retrieve_context(state: AgentState) -> AgentState:
    """Objetivo 2 del PDF: recupera contexto relevante del historial
    persistente del usuario (Qdrant) para la ultima consulta."""
    last_message = state["messages"][-1]["content"]
    context = await vector_store.search(str(state["user_id"]), last_message)
    return {**state, "rag_context": context}


def _to_langchain_messages(state: AgentState) -> list:
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if state.get("rag_context"):
        context_text = "\n".join(f"- {fragment}" for fragment in state["rag_context"])
        messages.append(SystemMessage(content=f"Contexto relevante del historial del usuario:\n{context_text}"))
    for entry in state["messages"]:
        if entry["role"] == "user":
            messages.append(HumanMessage(content=entry["content"]))
        else:
            messages.append(AIMessage(content=entry["content"]))
    return messages


def _extract_text(content) -> str:
    """Extrae texto plano de ai_message.content, que en langchain_google_genai
    puede ser un str o una lista de partes/bloques de texto."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
            elif hasattr(part, "text"):
                parts.append(str(part.text))
            else:
                parts.append(str(part))
        return "".join(parts)
    return str(content or "")


async def call_llm(state: AgentState) -> AgentState:
    """Llama a Gemini con el historial + contexto RAG. Si el LLM decide usar
    una tool, la deja en state['tool_call']; si no, deja la respuesta final
    en state['response']."""
    messages = _to_langchain_messages(state)
    if state.get("tool_result") is not None:
        messages.append(
            ToolMessage(
                content=json.dumps(state["tool_result"], default=str),
                tool_call_id=state["tool_call"]["id"],
            )
        )
    ai_message = await _get_llm().ainvoke(messages)

    if ai_message.tool_calls:
        call = ai_message.tool_calls[0]
        return {**state, "tool_call": {"id": call["id"], "name": call["name"], "arguments": call["args"]}}
    return {**state, "response": _extract_text(ai_message.content), "tool_call": None}


async def call_tool(state: AgentState) -> AgentState:
    """Invoca la tool decidida por el LLM en tools_service y guarda el
    resultado para que call_llm redacte la respuesta final con el."""
    tool_call = state["tool_call"]
    result = await invoke_tool(tool_call["name"], tool_call["arguments"], state["bearer_token"])
    return {**state, "tool_result": result}


async def generate_proactive_suggestion(state: AgentState) -> AgentState:
    """Objetivo 4 del PDF: analiza el historial reciente de activity_logs del
    usuario y, si detecta un patron simple (tareas pospuestas repetidamente),
    agrega una sugerencia proactiva a la respuesta."""
    since = datetime.now(timezone.utc) - timedelta(days=14)
    cursor = activity_logs.find(
        {"user_id": str(state["user_id"]), "created_at": {"$gte": since}}
    )
    kinds = Counter([doc["kind"] async for doc in cursor])

    suggestion = ""
    if kinds.get("task_postponed", 0) >= 3:
        suggestion = (
            "\n\nNote que has pospuesto varias tareas ultimamente. "
            "Si quieres, puedo ayudarte a dividir tu proxima tarea grande en "
            "pasos mas pequenos, o buscar un hueco libre en tu calendario para ella."
        )

    base_response = _extract_text(state.get("response", ""))
    return {**state, "response": base_response + suggestion}
