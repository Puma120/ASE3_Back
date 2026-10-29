"""Compactacion de la memoria a corto plazo. Cuando se acumulan mas de
`ventana + compaction_threshold` mensajes sin resumir, los mas viejos (todo
menos la ventana reciente) se funden con el resumen previo en uno nuevo,
guardado por usuario en Mongo (`chat_summaries`). El resumen no expira: sigue
vivo despues de que el TTL borre los mensajes de `chat_history`.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.db.mongo import chat_history, chat_summaries

log = logging.getLogger("agent.summary")

SUMMARY_PROMPT = (
    "Mantienes la memoria de una conversacion entre un usuario con TDAH y su asistente. "
    "Fusiona el resumen previo con los mensajes nuevos en un solo resumen en espanol, "
    "maximo 150 palabras, en vinetas cortas. Conserva solo datos duraderos: "
    "fechas, horas, nombres, compromisos, preferencias, decisiones y cosas pendientes. "
    "Descarta saludos, relleno y detalles que ya no sirven. Responde solo con el resumen."
)

_llm = None
# Un solo compactador por usuario a la vez; si ya hay uno corriendo se omite.
_locks: dict[str, asyncio.Lock] = {}


def _get_llm() -> ChatGoogleGenerativeAI:
    """Lazy init por la misma razon que nodes._get_llm (API key vacia en import)."""
    global _llm
    if _llm is None:
        _llm = ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            google_api_key=settings.gemini_api_key,
            temperature=0,
            max_retries=settings.llm_max_retries,
            timeout=settings.llm_timeout_seconds,
        )
    return _llm


async def _summarize(previous: str, messages: list[dict[str, str]]) -> str:
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    body = f"Resumen previo:\n{previous or '(ninguno)'}\n\nMensajes nuevos:\n{transcript}"
    reply = await _get_llm().ainvoke([SystemMessage(content=SUMMARY_PROMPT), HumanMessage(content=body)])
    return reply.text.strip()


async def get_summary(user_id: UUID) -> str:
    doc = await chat_summaries.find_one({"_id": str(user_id)})
    return doc["summary"] if doc else ""


async def maybe_compact(user_id: UUID, window: int | None = None) -> bool:
    """Resume los mensajes viejos si se paso el umbral. True si compacto."""
    uid = str(user_id)
    window = window or settings.short_term_memory_window
    lock = _locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return False
    async with lock:
        doc = await chat_summaries.find_one({"_id": uid}) or {}
        query: dict = {"user_id": uid}
        if doc.get("summarized_until"):
            query["created_at"] = {"$gt": doc["summarized_until"]}
        sin_resumir = [d async for d in chat_history.find(query).sort("created_at", 1)]
        if len(sin_resumir) <= window + settings.compaction_threshold:
            return False

        viejos = sin_resumir[:-window]
        resumen = await _summarize(
            doc.get("summary", ""), [{"role": d["role"], "content": d["content"]} for d in viejos]
        )
        await chat_summaries.replace_one(
            {"_id": uid},
            {
                "_id": uid,
                "summary": resumen,
                "summarized_until": viejos[-1]["created_at"],
                "updated_at": datetime.now(timezone.utc),
            },
            upsert=True,
        )
        return True
