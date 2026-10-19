"""Cliente Qdrant para RAG: indexado y busqueda semantica del historial/contexto
del usuario.

index_document()/search() miden contra los KPI de latencia/precision de la
Tabla 2.1 del PDF de tesina (latencia <300ms, tokens<500, precision>=90%).
"""

import re
import time
import uuid

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings

qdrant_client = QdrantClient(url=settings.qdrant_url)

_EMBEDDING_SIZE = 3072  # gemini-embedding-001, dimension por defecto

_embeddings = None


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Lazy init: construirlo en el import falla si GEMINI_API_KEY esta
    vacio (pydantic valida el key al crear el objeto), lo cual tumbaria el
    servicio completo antes de tener credenciales reales."""
    global _embeddings
    if _embeddings is None:
        _embeddings = GoogleGenerativeAIEmbeddings(
            model=f"models/{settings.gemini_embedding_model}",
            google_api_key=settings.gemini_api_key,
        )
    return _embeddings


def ensure_collection() -> None:
    """Crea la coleccion de Qdrant si no existe todavia (idempotente)."""
    if not qdrant_client.collection_exists(settings.qdrant_collection_name):
        qdrant_client.create_collection(
            collection_name=settings.qdrant_collection_name,
            vectors_config=qmodels.VectorParams(
                size=_EMBEDDING_SIZE, distance=qmodels.Distance.COSINE
            ),
        )


_SMALL_TALK = {
    "hola", "buenas", "buenos", "buenas", "dias", "tardes", "noches", "gracias", "ok", "okay", "vale",
    "si", "no", "claro", "listo", "perfecto", "genial", "bien", "bueno", "entiendo", "ya", "va",
    "adios", "hasta", "luego", "chao", "muchas", "por", "favor", "que", "tal", "como", "estas",
}


def is_worth_indexing(user_message: str, response: str) -> bool:
    """Descarta saludos, acuses y respuestas vacias: indexarlos solo mete ruido
    que luego compite con los recuerdos utiles en la busqueda."""
    words = re.findall(r"\w+", user_message.lower())
    if not response.strip() or not words:
        return False
    return not all(w in _SMALL_TALK for w in words)


async def index_document(user_id: str, text: str) -> None:
    """Embebe `text` y lo guarda asociado a `user_id` para recuperacion futura."""
    ensure_collection()
    vector = await _get_embeddings().aembed_query(text)
    qdrant_client.upsert(
        collection_name=settings.qdrant_collection_name,
        points=[
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"user_id": user_id, "text": text, "created_at": time.time()},
            )
        ],
    )


def purge_expired() -> None:
    """Borra los fragmentos mas viejos que rag_retention_days (0 = desactivado).
    Los puntos sin `created_at` (anteriores a este campo) nunca coinciden."""
    if not settings.rag_retention_days or not qdrant_client.collection_exists(settings.qdrant_collection_name):
        return
    limite = time.time() - settings.rag_retention_days * 86400
    qdrant_client.delete(
        collection_name=settings.qdrant_collection_name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(must=[qmodels.FieldCondition(key="created_at", range=qmodels.Range(lt=limite))])
        ),
    )


async def search(
    user_id: str,
    query: str,
    top_k: int | None = None,
    min_score: float | None = None,
    exclude_user_messages: list[str] | None = None,
) -> list[str]:
    """Devuelve hasta `top_k` fragmentos de `user_id` con similitud >= `min_score`.
    Omite los intercambios cuyo mensaje de usuario esta en `exclude_user_messages`
    (los que ya van literales en la ventana corta)."""
    ensure_collection()
    top_k = top_k or settings.rag_top_k
    min_score = settings.rag_min_score if min_score is None else min_score
    excluidos = {f"Usuario: {m}\n" for m in (exclude_user_messages or [])}
    vector = await _get_embeddings().aembed_query(query)
    results = qdrant_client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=vector,
        # Margen para que descartar los de la ventana no deje el top-k corto.
        limit=top_k + len(excluidos),
        score_threshold=min_score,
        query_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=user_id))]
        ),
    )
    textos = [p.payload["text"] for p in results.points if not any(p.payload["text"].startswith(e) for e in excluidos)]
    return textos[:top_k]
