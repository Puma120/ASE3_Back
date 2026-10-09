"""Como entra el contexto recuperado al prompt del LLM."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph import nodes
from app.memory import vector_store
from tests.support.entorno import CONTEXTO_USUARIO_FIJO
from tests.support.historial import USUARIO_A

FRAGMENTO = "Usuario: Mi consulta en el IMSS es el jueves a las 10:30\nAsistente: Anotada."


def _estado(**extra):
    return {
        "user_id": USUARIO_A,
        "bearer_token": "token",
        "messages": [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "hola, en que te ayudo"},
            {"role": "user", "content": "a que hora es mi consulta?"},
        ],
        **extra,
    }


def test_el_prompt_incluye_el_bloque_de_contexto_recuperado_en_orden():
    mensajes = nodes._to_langchain_messages(
        _estado(user_context=CONTEXTO_USUARIO_FIJO, rag_context=[FRAGMENTO, "otro fragmento"])
    )

    assert [type(m) for m in mensajes] == [
        SystemMessage, SystemMessage, SystemMessage, HumanMessage, AIMessage, HumanMessage
    ]
    assert mensajes[0].content == nodes.SYSTEM_PROMPT
    assert mensajes[1].content == CONTEXTO_USUARIO_FIJO
    assert mensajes[2].content == (
        f"Contexto relevante del historial del usuario:\n- {FRAGMENTO}\n- otro fragmento"
    )
    assert mensajes[-1].content == "a que hora es mi consulta?"


def test_sin_contexto_recuperado_no_hay_bloque():
    mensajes = nodes._to_langchain_messages(_estado(user_context=CONTEXTO_USUARIO_FIJO, rag_context=[]))

    assert not any("Contexto relevante" in m.content for m in mensajes)


async def test_retrieve_context_busca_el_ultimo_mensaje_con_el_top_k_del_usuario(monkeypatch):
    llamadas = []

    async def search_falso(user_id, query, top_k=None):
        llamadas.append((user_id, query, top_k))
        return [FRAGMENTO]

    monkeypatch.setattr(vector_store, "search", search_falso)

    estado = await nodes.retrieve_context(_estado(params={"rag_top_k": 3}))

    assert llamadas == [(str(USUARIO_A), "a que hora es mi consulta?", 3)]
    assert estado["rag_context"] == [FRAGMENTO]
    assert estado["user_context"] == CONTEXTO_USUARIO_FIJO


async def test_retrieve_context_sigue_sin_rag_si_qdrant_falla(monkeypatch):
    async def search_roto(*args, **kwargs):
        raise ConnectionError("Qdrant caido")

    monkeypatch.setattr(vector_store, "search", search_roto)

    estado = await nodes.retrieve_context(_estado())

    assert estado["rag_context"] == []
    assert estado["user_context"] == CONTEXTO_USUARIO_FIJO


async def test_retrieve_context_recupera_de_qdrant(fake_embeddings):
    await vector_store.index_document(str(USUARIO_A), FRAGMENTO)
    await vector_store.index_document(str(USUARIO_A), "Usuario: pon alarma a las 6:30\nAsistente: Listo.")

    estado = await nodes.retrieve_context(_estado(params={"rag_top_k": 1}))

    assert estado["rag_context"] == [FRAGMENTO]
