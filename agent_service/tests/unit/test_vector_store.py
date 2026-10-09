"""Almacenamiento y recuperacion en Qdrant (en memoria, embeddings deterministas)."""

from app.core.config import settings
from app.memory import vector_store
from tests.support.historial import USUARIO_A, USUARIO_B

DOCUMENTOS = [
    "Usuario: Mi consulta en el IMSS es el jueves a las 10:30\nAsistente: Anotada tu consulta en el IMSS.",
    "Usuario: Tengo turno en la cafeteria martes y jueves a las 4\nAsistente: Turnos martes y jueves, 16:00.",
    "Usuario: Divide el proyecto de Bases de Datos en pasos\nAsistente: Paso 1: diagrama entidad-relacion.",
    "Usuario: La renta se paga el dia 1\nAsistente: Renta: dia 1, recordatorio el 28.",
    "Usuario: El parcial de Calculo es el lunes 26\nAsistente: Parcial: lunes 26 a las 7:00.",
    "Usuario: Me tomo la pastilla a las 7:10\nAsistente: Alarma diaria a las 7:10.",
    "Usuario: La beca cierra el 20 de octubre\nAsistente: Fecha limite de la beca: 20 de octubre.",
    "Usuario: Quiero dormirme a las 11:30\nAsistente: Hora de dormir: 23:30.",
]


async def _indexar(user_id, textos):
    for texto in textos:
        await vector_store.index_document(str(user_id), texto)


async def test_ensure_collection_es_idempotente(fake_embeddings, qdrant):
    vector_store.ensure_collection()
    vector_store.ensure_collection()

    coleccion = qdrant.get_collection(settings.qdrant_collection_name)
    assert coleccion.config.params.vectors.size == fake_embeddings.size


async def test_index_document_guarda_usuario_y_texto(fake_embeddings, qdrant):
    await vector_store.index_document(str(USUARIO_A), DOCUMENTOS[0])

    puntos, _ = qdrant.scroll(settings.qdrant_collection_name, with_payload=True)
    assert [p.payload for p in puntos] == [{"user_id": str(USUARIO_A), "text": DOCUMENTOS[0]}]


async def test_el_fragmento_relevante_sale_primero(fake_embeddings):
    await _indexar(USUARIO_A, DOCUMENTOS)

    resultados = await vector_store.search(str(USUARIO_A), "a que hora es mi consulta en el IMSS?")

    assert "IMSS" in resultados[0]


async def test_respeta_top_k_y_su_default(fake_embeddings):
    await _indexar(USUARIO_A, DOCUMENTOS)

    assert len(await vector_store.search(str(USUARIO_A), "consulta", top_k=3)) == 3
    assert len(await vector_store.search(str(USUARIO_A), "consulta")) == settings.rag_top_k


async def test_no_recupera_fragmentos_de_otro_usuario(fake_embeddings):
    await _indexar(USUARIO_A, DOCUMENTOS[:1])
    privado_b = "Usuario: Mi consulta en el IMSS es el martes a las 8:20\nAsistente: Anotada, martes 8:20."
    await _indexar(USUARIO_B, [privado_b, DOCUMENTOS[0]])

    resultados = await vector_store.search(str(USUARIO_A), "consulta en el IMSS", top_k=5)

    assert resultados == [DOCUMENTOS[0]]


async def test_usuario_sin_historial_no_recupera_nada(fake_embeddings):
    await _indexar(USUARIO_B, DOCUMENTOS)

    assert await vector_store.search(str(USUARIO_A), "consulta en el IMSS") == []
