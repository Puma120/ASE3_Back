from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.agent import router as agent_router
from app.api.routes.chat import router as chat_router
from app.memory.short_term import ensure_indexes


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_indexes()
    yield

app = FastAPI(
    title="TDAH Agent - Agent Service",
    description="Nucleo conversacional (LangGraph + LLM). RAG sobre Qdrant, invoca tools_service, conexion a proveedor LLM externo.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(chat_router)
app.include_router(agent_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent_service"}
