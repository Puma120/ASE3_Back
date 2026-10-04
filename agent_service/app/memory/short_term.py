"""Memoria a corto plazo: los ultimos N mensajes de la conversacion activa
(ventana configurable por usuario), guardados en Mongo (`chat_history`) para
sobrevivir reinicios/redeploys. El historial largo vive en Qdrant
(vector_store.py).
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.core.config import settings
from app.db.mongo import chat_history

RETENTION_DAYS = 30


async def ensure_indexes() -> None:
    await chat_history.create_index([("user_id", 1), ("created_at", -1)])
    await chat_history.create_index(
        "created_at", expireAfterSeconds=int(timedelta(days=RETENTION_DAYS).total_seconds())
    )


async def get_history(user_id: UUID, window: int | None = None) -> list[dict[str, str]]:
    window = window or settings.short_term_memory_window
    cursor = chat_history.find({"user_id": str(user_id)}).sort("created_at", -1).limit(window)
    docs = [doc async for doc in cursor]
    return [{"role": d["role"], "content": d["content"]} for d in reversed(docs)]


async def append_exchange(user_id: UUID, user_message: str, assistant_message: str) -> None:
    now = datetime.now(timezone.utc)
    await chat_history.insert_many(
        [
            {"user_id": str(user_id), "role": "user", "content": user_message, "created_at": now},
            {
                "user_id": str(user_id),
                "role": "assistant",
                "content": assistant_message,
                "created_at": now + timedelta(milliseconds=1),
            },
        ]
    )
