"""Endpoint conversacional principal: /chat (invoca el grafo compilado de
app/graph/builder.py).
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from langchain_core.exceptions import ModelAPIError, ModelRateLimitError

from app.clients.tools_client import call_tool
from app.core import session
from app.core.deps import get_current_user_id
from app.graph.builder import agent_graph
from app.graph.nodes import calendar_sync_prompt
from app.memory import params as params_store
from app.memory import profile
from app.memory import summary as summary_store
from app.memory import vector_store
from app.memory.short_term import append_exchange, get_history, get_recent_messages
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, DeviceCommand, HistoryMessage

log = logging.getLogger("agent.chat")

router = APIRouter(prefix="/agent", tags=["chat"])

# Referencias fuertes para que las tareas en segundo plano no las recoja el GC.
_background: set[asyncio.Task] = set()

MAX_SYNC_DAYS = 800  # un poco mas de 2 anos


async def _existing_titles(bearer_token: str) -> str:
    """Titulos de lo que ya hay en el calendario las proximas 2 semanas, para no duplicar la rutina.
    Se lee aqui y no con la tool list_events porque esa bloquea las escrituras del turno."""
    now = datetime.now(timezone.utc)
    window = {"window_start": now.isoformat(), "window_end": (now + timedelta(days=14)).isoformat()}
    result = await call_tool("list_events", window, bearer_token)
    titles = {str(e.get("summary", ""))[:60].replace("\n", " ") for e in result.get("items", []) if isinstance(e, dict)}
    return "; ".join(sorted(t for t in titles if t))[:600]


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

    calendar_sync = ""
    if body.calendar_sync_until:
        if not date.today() <= body.calendar_sync_until <= date.today() + timedelta(days=MAX_SYNC_DAYS):
            raise HTTPException(status_code=422, detail="calendar_sync_until fuera de rango")
        existing = await _existing_titles(session.bearer_token.get())
        calendar_sync = calendar_sync_prompt(body.calendar_sync_until.isoformat(), existing)

    try:
        result = await agent_graph.ainvoke(
            {
                "user_id": user_id,
                "messages": messages,
                "params": params.model_dump(),
                "timezone": body.timezone or "",
                "onboarding": body.onboarding,
                "calendar_sync": calendar_sync,
                "client": body.client or "",
                "location": {"lat": body.lat, "lng": body.lng} if body.lat is not None and body.lng is not None else {},
            }
        )
    except (ModelRateLimitError, ModelAPIError):
        # Gemini sigue sin responder tras los reintentos (cuota o caida): 503 con
        # mensaje legible en vez de un 500 generico; el cliente ofrece Reintentar.
        log.exception("Gemini no disponible tras reintentos")
        raise HTTPException(
            status_code=503,
            detail="El asistente esta saturado, intenta de nuevo en unos segundos",
            headers={"Retry-After": "15"},
        )

    if result.get("events_created") and (calendar_sync or body.onboarding):
        try:
            await profile.set_calendar_sync(user_id, profile.DONE)
        except Exception:
            log.exception("No se pudo marcar la rutina como agendada")

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
