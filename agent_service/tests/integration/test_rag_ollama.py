"""Recuperacion semantica real: historial sintetico indexado con el modelo de
embeddings local (qwen3-embedding) y el codigo de produccion. Los umbrales son
los "aceptables" de la Tabla tab:kpi-obj2; la medicion fina con reporte esta
en tests/kpi/eval_obj2.py."""

import asyncio
import statistics

import pytest
from qdrant_client import QdrantClient

from app.core.config import settings
from app.memory import vector_store
from tests.support import local_models, rag_eval

pytestmark = pytest.mark.ollama

# Prueba funcional con las consultas claras; la calificacion del KPI con todos
# los niveles de dificultad la hace tests/kpi/eval_obj2.py.
NIVELES_CLAROS = ("directa", "parafraseada")


@pytest.fixture(scope="module")
def qdrant_sembrado():
    """Indexa el dataset una sola vez por modulo (tarda unos segundos)."""
    motivo = local_models.motivo_no_disponible(local_models.OLLAMA_EMBEDDING_MODEL)
    if motivo:
        pytest.skip(motivo)
    dataset = rag_eval.cargar_dataset()
    cliente = QdrantClient(":memory:")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(vector_store, "qdrant_client", cliente)
        mp.setattr(vector_store, "_embeddings", local_models.build_embeddings())
        mp.setattr(vector_store, "_EMBEDDING_SIZE", local_models.OLLAMA_EMBEDDING_SIZE)
        asyncio.run(rag_eval.sembrar(dataset))
    assert cliente.count(settings.qdrant_collection_name).count == rag_eval.total_intercambios(dataset)
    return dataset, cliente


@pytest.fixture
def dataset(monkeypatch, qdrant_sembrado, ollama_embeddings):
    datos, cliente = qdrant_sembrado
    monkeypatch.setattr(vector_store, "qdrant_client", cliente)
    return datos


async def test_el_fragmento_mas_relevante_sale_primero_y_sin_fugas(dataset):
    resultado = await rag_eval.evaluar_precision(dataset, settings.rag_top_k, niveles=NIVELES_CLAROS)

    assert resultado["fugas"] == 0
    assert resultado["hit@1"] >= 0.9, _peores(resultado)


async def test_precision_aceptable_en_los_primeros_tres(dataset):
    # Con top_k fijo y sin umbral de score, la precision baja al crecer k: el
    # valor con el top_k de produccion lo reporta tests/kpi/eval_obj2.py.
    resultado = await rag_eval.evaluar_precision(dataset, 3, niveles=NIVELES_CLAROS)

    assert resultado["precision"] >= 0.75, _peores(resultado)


async def test_latencia_de_recuperacion_aceptable(dataset):
    resultado = await rag_eval.evaluar_precision(dataset, settings.rag_top_k, niveles=NIVELES_CLAROS)

    assert statistics.mean(resultado["latencias_search_ms"]) < 800


def _peores(resultado: dict) -> str:
    peores = sorted(resultado["operaciones"], key=lambda c: c["precision"])[:5]
    return "Consultas con menor precision: " + "; ".join(
        f"{c['id']}={c['precision']:.0%}" for c in peores
    )
