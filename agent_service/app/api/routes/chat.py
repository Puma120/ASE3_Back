"""Endpoint conversacional principal: /chat (invoca el grafo compilado de
app/graph/builder.py).
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.core import session
from app.core.deps import get_current_user_id
from app.graph.builder import agent_graph
from app.memory import params as params_store
from app.memory import summary as summary_store
from app.memory import vector_store
from app.memory.short_term import append_exchange, get_history, get_recent_messages
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, DeviceCommand, HistoryMessage

log = logging.getLogger("agent.chat")

router = APIRouter(prefix="/agent", tags=["chat"])

# Referencias fuertes para que las tareas en segundo plano no las recoja el GC.
_background: set[asyncio.Task] = set()


async def _index_exchange(user_id: str, user_message: str, response: str) -> None:
    """Alimenta el RAG con el intercambio y compacta la memoria corta si ya
    se acumulo (sin bloquear la respuesta)."""
    try:
        if vector_store.is_worth_indexing(user_message, response):
            await vector_store.index_document(user_id, f"Usuario: {user_message}\nAsistente: {response}")
    except Exception:
        log.exception("No se pudo indexar el intercambio en Qdrant")
    try:
        await summary_store.maybe_compact(uuid.UUID(user_id))
    except Exception:
        log.exception("No se pudo compactar la memoria corta")


@router.post("/chat", response_model=ChatMessageResponse)
async def chat(
    body: ChatMessageRequest,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ChatMessageResponse:
    # Fuera del estado del grafo para que no quede en las trazas (app/core/session.py).
    session.bearer_token.set(request.headers["Authorization"].removeprefix("Bearer "))

    params = await params_store.get_params(user_id)
    history = await get_history(user_id, params.short_term_memory_window)
    messages = history + [{"role": "user", "content": body.message}]

    result = await agent_graph.ainvoke(
        {
            "user_id": user_id,
            "messages": messages,
            "params": params.model_dump(),
            "timezone": body.timezone or "",
            "onboarding": body.onboarding,
            "client": body.client or "",
            "location": {"lat": body.lat, "lng": body.lng} if body.lat is not None and body.lng is not None else {},
        }
    )

    await append_exchange(user_id, body.message, result["response"])
    task = asyncio.create_task(_index_exchange(str(user_id), body.message, result["response"]))
    _background.add(task)
    task.add_done_callback(_background.discard)

    return ChatMessageResponse(
        response=result["response"],
        device_commands=[DeviceCommand(**c) for c in result.get("device_commands", [])],
        onboarding_done=result.get("onboarding_done", False),
    )


@router.get("/history", response_model=list[HistoryMessage])
async def history(
    limit: int = Query(default=30, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[HistoryMessage]:
    """Ultimos mensajes de la conversacion: al volver a la app el usuario ve en
    que iba (decision 5 del documento de diseno TDAH del front)."""
    return [HistoryMessage(**m) for m in await get_recent_messages(user_id, limit)]
