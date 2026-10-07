"""Ayudas para sembrar y observar la memoria del agente en las pruebas."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.api.routes import chat
from app.memory import short_term

USUARIO_A = uuid.UUID("11111111-1111-4111-8111-111111111111")
USUARIO_B = uuid.UUID("22222222-2222-4222-8222-222222222222")


async def sembrar_historial(user_id: UUID, intercambios: list[tuple[str, str]]) -> None:
    """Inserta los intercambios en Mongo con 2 minutos entre si, como una
    conversacion real. No usa append_exchange: dos llamadas seguidas en el
    mismo milisegundo intercalarian los mensajes al ordenar por created_at."""
    inicio = datetime.now(timezone.utc) - timedelta(days=1)
    documentos = []
    for i, (mensaje_usuario, respuesta) in enumerate(intercambios):
        momento = inicio + timedelta(minutes=2 * i)
        documentos += [
            {"user_id": str(user_id), "role": "user", "content": mensaje_usuario, "created_at": momento},
            {
                "user_id": str(user_id),
                "role": "assistant",
                "content": respuesta,
                "created_at": momento + timedelta(minutes=1),
            },
        ]
    await short_term.chat_history.insert_many(documentos)


async def indexar_historial(user_id: UUID, intercambios: list[tuple[str, str]]) -> None:
    """Indexa en Qdrant igual que /agent/chat despues de cada respuesta."""
    for mensaje_usuario, respuesta in intercambios:
        await chat._index_exchange(str(user_id), mensaje_usuario, respuesta)


async def esperar_indexado() -> None:
    """Espera las tareas de indexado que /agent/chat deja en segundo plano."""
    pendientes = list(chat._background)
    if pendientes:
        await asyncio.gather(*pendientes)
