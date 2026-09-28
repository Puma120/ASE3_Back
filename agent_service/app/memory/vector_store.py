"""Cliente Qdrant para RAG: indexado y busqueda semantica del historial/contexto
del usuario.

index_document()/search() miden contra los KPI de latencia/precision de la
Tabla 2.1 del PDF de tesina (latencia <300ms, tokens<500, precision>=90%).
"""

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
                payload={"user_id": user_id, "text": text},
            )
        ],
    )


async def search(user_id: str, query: str, top_k: int | None = None) -> list[str]:
    """Devuelve los `top_k` fragmentos mas relevantes para `query`, filtrados
    al historial de `user_id`."""
    ensure_collection()
    vector = await _get_embeddings().aembed_query(query)
    results = qdrant_client.query_points(
        collection_name=settings.qdrant_collection_name,
        query=vector,
        limit=top_k or settings.rag_top_k,
        query_filter=qmodels.Filter(
            must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=user_id))]
        ),
    )
    return [point.payload["text"] for point in results.points]
