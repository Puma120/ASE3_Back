"""Capas nuevas de memoria: filtro de ruido, umbral y exclusion en el RAG,
purga por antiguedad, compactacion en resumen y acciones pendientes."""

import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.graph import nodes
from app.memory import summary, vector_store, workflow
from tests.support.historial import USUARIO_A, USUARIO_B, sembrar_historial

IMSS = "Usuario: Mi consulta en el IMSS es el jueves a las 10:30\nAsistente: Anotada."
BECA = "Usuario: La beca cierra el 20 de octubre\nAsistente: Fecha limite anotada."


def test_el_filtro_descarta_saludos_y_acuses():
    assert not vector_store.is_worth_indexing("hola", "hola, en que te ayudo")
    assert not vector_store.is_worth_indexing("ok gracias", "de nada")
    assert not vector_store.is_worth_indexing("agenda algo", "   ")
    assert vector_store.is_worth_indexing("mi consulta es el jueves a las 10", "anotado")


async def test_el_umbral_descarta_lo_irrelevante(fake_embeddings, monkeypatch):
    await vector_store.index_document(str(USUARIO_A), IMSS)

    sin_umbral = await vector_store.search(str(USUARIO_A), "consulta IMSS", min_score=-1)
    estricto = await vector_store.search(str(USUARIO_A), "zzz qqq", min_score=0.99)

    assert sin_umbral == [IMSS]
    assert estricto == []


async def test_search_omite_lo_que_ya_va_en_la_ventana(fake_embeddings):
    await vector_store.index_document(str(USUARIO_A), IMSS)
    await vector_store.index_document(str(USUARIO_A), BECA)

    r = await vector_store.search(
        str(USUARIO_A), "consulta beca", min_score=-1,
        exclude_user_messages=["Mi consulta en el IMSS es el jueves a las 10:30"],
    )

    assert r == [BECA]


async def test_purge_expired_borra_solo_lo_viejo(fake_embeddings, qdrant, monkeypatch):
    await vector_store.index_document(str(USUARIO_A), IMSS)
    ahora = time.time()
    with monkeypatch.context() as m:
        m.setattr(vector_store.time, "time", lambda: ahora - 100 * 86400)
        await vector_store.index_document(str(USUARIO_A), BECA)
    monkeypatch.setattr(settings, "rag_retention_days", 30)

    vector_store.purge_expired()

    puntos, _ = qdrant.scroll(settings.qdrant_collection_name, with_payload=True)
    assert [p.payload["text"] for p in puntos] == [IMSS]


async def test_compacta_solo_al_pasar_el_umbral(monkeypatch):
    recibidos = []

    async def resumen_falso(previo, mensajes):
        recibidos.append((previo, len(mensajes)))
        return "- consulta IMSS jueves 10:30"

    monkeypatch.setattr(summary, "_summarize", resumen_falso)
    monkeypatch.setattr(settings, "compaction_threshold", 4)
    ventana = 2

    await sembrar_historial(USUARIO_A, [(f"u{i}", f"a{i}") for i in range(3)])  # 6 msgs = ventana+4
    assert await summary.maybe_compact(USUARIO_A, ventana) is False

    await sembrar_historial(USUARIO_A, [("u9", "a9")])  # 8 msgs > 6
    assert await summary.maybe_compact(USUARIO_A, ventana) is True

    assert recibidos == [("", 6)]  # todo menos la ventana
    assert await summary.get_summary(USUARIO_A) == "- consulta IMSS jueves 10:30"
    assert await summary.get_summary(USUARIO_B) == ""


async def test_el_resumen_previo_se_funde_con_lo_nuevo(monkeypatch):
    previos = []

    async def resumen_falso(previo, mensajes):
        previos.append(previo)
        return f"resumen{len(previos)}"

    monkeypatch.setattr(summary, "_summarize", resumen_falso)
    monkeypatch.setattr(settings, "compaction_threshold", 2)

    await sembrar_historial(USUARIO_A, [(f"u{i}", f"a{i}") for i in range(3)])
    await summary.maybe_compact(USUARIO_A, 2)
    ahora = datetime.now(timezone.utc)
    await summary.chat_history.insert_many(
        [
            {"user_id": str(USUARIO_A), "role": rol, "content": f"{rol}{i}", "created_at": ahora + timedelta(minutes=i)}
            for i, rol in enumerate(["user", "assistant"] * 3)
        ]
    )
    await summary.maybe_compact(USUARIO_A, 2)

    assert previos == ["", "resumen1"]


async def test_pendientes_se_guardan_se_acotan_y_se_limpian():
    for i in range(workflow.MAX_PENDING + 3):
        await workflow.add_pending(USUARIO_A, "create_task", {"n": i})
    await workflow.add_pending(USUARIO_A, "create_event", {"x": 1})

    pendientes = await workflow.get_pending(USUARIO_A)
    assert len(pendientes) == workflow.MAX_PENDING
    assert pendientes[-1]["tool"] == "create_event"
    assert await workflow.get_pending(USUARIO_B) == []

    await workflow.clear_pending(USUARIO_A, ["create_task"])
    assert [p["tool"] for p in await workflow.get_pending(USUARIO_A)] == ["create_event"]
    await workflow.clear_pending(USUARIO_A)
    assert await workflow.get_pending(USUARIO_A) == []


def test_el_prompt_incluye_resumen_y_pendientes_antes_del_rag():
    estado = {
        "user_id": USUARIO_A,
        "messages": [{"role": "user", "content": "hola"}],
        "summary": "- beca cierra 20 oct",
        "pending_actions": "Acciones pendientes: create_task",
        "rag_context": ["frag"],
    }

    textos = [m.content for m in nodes._to_langchain_messages(estado)]

    assert textos[1] == "Resumen de la conversacion anterior con el usuario:\n- beca cierra 20 oct"
    assert textos[2] == "Acciones pendientes: create_task"
    assert textos[3].startswith("Contexto relevante")
