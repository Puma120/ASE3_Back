"""Fixtures comunes. El entorno se configura antes de importar `app` para que
ninguna prueba use agent_service/.env (Gemini, bases reales) ni Railway."""

from tests.support.entorno import configurar_entorno

configurar_entorno("tdah_agent_memory_test")

import uuid  # noqa: E402

import httpx  # noqa: E402
import jwt  # noqa: E402
import pytest  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.graph import nodes  # noqa: E402
from app.memory import params as params_store  # noqa: E402
from app.memory import short_term, vector_store  # noqa: E402
from tests.support import local_models  # noqa: E402
from tests.support.entorno import CONTEXTO_USUARIO_FIJO, verificar_entorno  # noqa: E402
from tests.support.fake_embeddings import HashingEmbeddings, SinEmbeddings  # noqa: E402

verificar_entorno(settings)


def _llm_no_configurado(temperature: float, with_tools: bool = True):
    raise RuntimeError("Las pruebas no deben llamar a Gemini: usa la fixture ollama_llm o un grafo falso")


@pytest.fixture(autouse=True)
def mongo(monkeypatch):
    """Mongo en memoria en lugar de la base real."""
    db = AsyncMongoMockClient()[settings.mongo_db_name]
    monkeypatch.setattr(short_term, "chat_history", db["chat_history"])
    monkeypatch.setattr(params_store, "agent_params", db["agent_params"])
    monkeypatch.setattr(nodes, "activity_logs", db["activity_logs"])
    return db


@pytest.fixture(autouse=True)
def qdrant(monkeypatch):
    """Qdrant en memoria (en proceso) en lugar del servidor."""
    cliente = QdrantClient(":memory:")
    monkeypatch.setattr(vector_store, "qdrant_client", cliente)
    return cliente


@pytest.fixture(autouse=True)
def sin_modelos_en_linea(monkeypatch):
    """Por defecto ningun LLM ni embedding: cada prueba pide el suyo."""
    monkeypatch.setattr(vector_store, "_embeddings", SinEmbeddings())
    monkeypatch.setattr(nodes, "_get_llm", _llm_no_configurado)


@pytest.fixture(autouse=True)
def externos_falsos(monkeypatch):
    """auth_service, proactive_service y tools_service no estan levantados en
    las pruebas: contexto de usuario fijo y tools con respuesta vacia."""
    llamadas: list[tuple[str, dict]] = []

    async def contexto_fijo(bearer_token: str) -> str:
        return CONTEXTO_USUARIO_FIJO

    async def tool_vacia(tool_name: str, payload: dict, bearer_token: str) -> dict:
        llamadas.append((tool_name, payload))
        return {"items": []}

    monkeypatch.setattr(nodes, "build_user_context", contexto_fijo)
    monkeypatch.setattr(nodes, "invoke_tool", tool_vacia)
    return llamadas


@pytest.fixture
def fake_embeddings(monkeypatch):
    embeddings = HashingEmbeddings()
    monkeypatch.setattr(vector_store, "_embeddings", embeddings)
    monkeypatch.setattr(vector_store, "_EMBEDDING_SIZE", embeddings.size)
    return embeddings


@pytest.fixture
def ollama_embeddings(monkeypatch):
    motivo = local_models.motivo_no_disponible(local_models.OLLAMA_EMBEDDING_MODEL)
    if motivo:
        pytest.skip(motivo)
    embeddings = local_models.build_embeddings()
    monkeypatch.setattr(vector_store, "_embeddings", embeddings)
    monkeypatch.setattr(vector_store, "_EMBEDDING_SIZE", local_models.OLLAMA_EMBEDDING_SIZE)
    return embeddings


@pytest.fixture
def ollama_llm(monkeypatch):
    motivo = local_models.motivo_no_disponible(local_models.OLLAMA_CHAT_MODEL)
    if motivo:
        pytest.skip(motivo)
    monkeypatch.setattr(nodes, "_get_llm", local_models.get_llm_local())


@pytest.fixture
def auth_headers():
    def headers(user_id: uuid.UUID, secreto: str | None = None) -> dict[str, str]:
        token = jwt.encode({"sub": str(user_id)}, secreto or settings.jwt_secret_key, settings.jwt_algorithm)
        return {"Authorization": f"Bearer {token}"}

    return headers


@pytest.fixture
async def client():
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=None
    ) as c:
        yield c
