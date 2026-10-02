"""Parametros del agente por usuario (PDF 2.2.1: ventana de memoria corta,
top-k del RAG, temperatura). Persisten en Mongo (coleccion `agent_params`,
schemaless); si el usuario no los ha editado se usan los defaults del entorno.
"""

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.config import settings
from app.db.mongo import agent_params


class AgentParams(BaseModel):
    short_term_memory_window: int = Field(ge=2, le=50)
    rag_top_k: int = Field(ge=1, le=20)
    llm_temperature: float = Field(ge=0.0, le=1.0)


class AgentParamsUpdate(BaseModel):
    short_term_memory_window: int | None = Field(default=None, ge=2, le=50)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    llm_temperature: float | None = Field(default=None, ge=0.0, le=1.0)


def defaults() -> AgentParams:
    return AgentParams(
        short_term_memory_window=settings.short_term_memory_window,
        rag_top_k=settings.rag_top_k,
        llm_temperature=settings.llm_temperature,
    )


async def get_params(user_id: UUID) -> AgentParams:
    doc = await agent_params.find_one({"_id": str(user_id)}) or {}
    merged = defaults().model_dump() | {k: v for k, v in doc.items() if k != "_id"}
    return AgentParams(**merged)


async def update_params(user_id: UUID, patch: AgentParamsUpdate) -> AgentParams:
    changes = patch.model_dump(exclude_none=True)
    if changes:
        await agent_params.update_one({"_id": str(user_id)}, {"$set": changes}, upsert=True)
    return await get_params(user_id)
