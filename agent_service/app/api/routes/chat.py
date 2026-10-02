"""Endpoint conversacional principal: /chat (invoca el grafo compilado de
app/graph/builder.py).
"""

import uuid

from fastapi import APIRouter, Depends, Request

from app.core.deps import get_current_user_id
from app.graph.builder import agent_graph
from app.memory import params as params_store
from app.memory.short_term import append_exchange, get_history
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse

router = APIRouter(prefix="/agent", tags=["chat"])


@router.post("/chat", response_model=ChatMessageResponse)
async def chat(
    body: ChatMessageRequest,
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ChatMessageResponse:
    bearer_token = request.headers["Authorization"].removeprefix("Bearer ")

    params = await params_store.get_params(user_id)
    history = get_history(user_id)
    messages = history + [{"role": "user", "content": body.message}]

    result = await agent_graph.ainvoke(
        {"user_id": user_id, "bearer_token": bearer_token, "messages": messages, "params": params.model_dump()}
    )

    window = params.short_term_memory_window
    append_exchange(user_id, "user", body.message, window)
    append_exchange(user_id, "assistant", result["response"], window)

    return ChatMessageResponse(response=result["response"])
