"""Memoria a corto plazo: retiene solo los ultimos N intercambios de la sesion
activa (SHORT_TERM_MEMORY_WINDOW), delegando el historial completo a la
memoria persistente (vector_store.py) para evitar saturar el contexto del LLM.

Sesion = conversacion activa, en memoria del proceso (no persiste reinicios;
el historial de largo plazo vive en Qdrant via vector_store.py).
"""

from collections import defaultdict
from uuid import UUID

from app.core.config import settings

_sessions: dict[UUID, list[dict[str, str]]] = defaultdict(list)


def get_history(user_id: UUID) -> list[dict[str, str]]:
    return list(_sessions[user_id])


def append_exchange(
    user_id: UUID, role: str, content: str, window: int | None = None
) -> None:
    history = _sessions[user_id]
    history.append({"role": role, "content": content})
    window = window or settings.short_term_memory_window
    if len(history) > window:
        del history[: len(history) - window]
