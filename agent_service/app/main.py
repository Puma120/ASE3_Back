from fastapi import FastAPI

from app.api.routes.agent import router as agent_router
from app.api.routes.chat import router as chat_router

app = FastAPI(
    title="TDAH Agent - Agent Service",
    description="Nucleo conversacional (LangGraph + LLM). RAG sobre Qdrant, invoca tools_service, conexion a proveedor LLM externo.",
    version="0.1.0",
)

app.include_router(chat_router)
app.include_router(agent_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "agent_service"}
