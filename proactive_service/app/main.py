import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.proactive import router as proactive_router
from app.core.config import settings
from app.db.mongo import ensure_indexes
from app.engine.tick import tick_loop

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await ensure_indexes()
    task = asyncio.create_task(tick_loop()) if settings.tick_enabled else None
    yield
    if task:
        task.cancel()


app = FastAPI(
    title="TDAH Agent - Proactive Service",
    description="Motor proactivo: tick silencioso por usuario, recordatorios inteligentes y envio de push.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(proactive_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "proactive_service"}
