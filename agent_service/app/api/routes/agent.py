"""Endpoints de lectura/configuracion del agente: sugerencia proactiva y
parametros por usuario (PDF 2.2.1)."""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import get_current_user_id
from app.graph.nodes import proactive_suggestion_text
from app.memory import params as params_store
from app.memory.params import AgentParams, AgentParamsUpdate
from app.schemas.chat import SuggestionResponse

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/suggestion", response_model=SuggestionResponse)
async def suggestion(user_id: uuid.UUID = Depends(get_current_user_id)) -> SuggestionResponse:
    text = await proactive_suggestion_text(str(user_id))
    return SuggestionResponse(suggestion=text or None)


@router.get("/params", response_model=AgentParams)
async def read_params(user_id: uuid.UUID = Depends(get_current_user_id)) -> AgentParams:
    return await params_store.get_params(user_id)


@router.patch("/params", response_model=AgentParams)
async def patch_params(
    body: AgentParamsUpdate, user_id: uuid.UUID = Depends(get_current_user_id)
) -> AgentParams:
    return await params_store.update_params(user_id, body)
