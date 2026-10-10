"""Endpoint conversacional principal: /chat (invoca el grafo compilado de
app/graph/builder.py).
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, Query, Request

from app.core.deps import get_current_user_id
from app.graph.builder import agent_graph
from app.memory import params as params_store
from app.memory import vector_store
from app.memory.short_term import append_exchange, get_history, get_recent_messages
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, DeviceCommand, HistoryMessage

log = logging.getLogger("agent.chat")

router = APIRouter(prefix="/agent", tags=["chat"])

# Referencias fuertes para que las tareas en segundo plano no las recoja el GC.
_background: set[asyncio.Task] = set()


async def _index_exchange(user_id: str, user_message: str, response: str) -> None:
    """Alimenta el RAG con el intercambio (sin bloquear la respuesta)."""
    try:
        await vector_store.index_document(user_id, f"Usuario: {user_message}\nAsistente: {response}")
    except Exception:
        log.exception("No se pudo indexar el intercambio en Qdrant")


@router.post("/chat", response_model=ChatMessageResponse)
async def chat(
    body: ChatMessageRequest,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ChatMessageResponse:
    bearer_token = request.headers["Authorization"].removeprefix("Bearer ")

    params = await params_store.get_params(user_id)
    history = await get_history(user_id, params.short_term_memory_window)
    messages = history + [{"role": "user", "content": body.message}]

    result = await agent_graph.ainvoke(
        {
            "user_id": user_id,
            "bearer_token": bearer_token,
            "messages": messages,
            "params": params.model_dump(),
            "timezone": body.timezone or "",
        }
    )

    await append_exchange(user_id, body.message, result["response"])
    task = asyncio.create_task(_index_exchange(str(user_id), body.message, result["response"]))
    _background.add(task)
    task.add_done_callback(_background.discard)

    return ChatMessageResponse(
        response=result["response"],
        device_commands=[DeviceCommand(**c) for c in result.get("device_commands", [])],
    )


@router.get("/history", response_model=list[HistoryMessage])
async def history(
    limit: int = Query(default=30, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[HistoryMessage]:
    """Ultimos mensajes de la conversacion: al volver a la app el usuario ve en
    que iba (decision 5 del documento de diseno TDAH del front)."""
    return [HistoryMessage(**m) for m in await get_recent_messages(user_id, limit)]
