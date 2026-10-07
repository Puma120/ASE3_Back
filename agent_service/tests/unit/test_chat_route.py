"""/agent/chat: arma la ventana corta, guarda el intercambio en Mongo y lo
indexa en Qdrant para recuperarlo despues. El grafo es falso (sin LLM)."""

import pytest

from app.api.routes import chat
from app.memory import params as params_store
from app.memory import short_term, vector_store
from tests.support.historial import USUARIO_A, esperar_indexado, sembrar_historial

DOCE_INTERCAMBIOS = [(f"pregunta {i}", f"respuesta {i}") for i in range(1, 13)]


class GrafoFalso:
    def __init__(self, respuesta: str = "Respuesta de prueba"):
        self.respuesta = respuesta
        self.recibido = None

    async def ainvoke(self, estado):
        self.recibido = estado
        return {"response": self.respuesta, "device_commands": []}


@pytest.fixture
def grafo(monkeypatch):
    grafo = GrafoFalso()
    monkeypatch.setattr(chat, "agent_graph", grafo)
    return grafo


async def test_el_grafo_recibe_solo_la_ventana_del_usuario(client, auth_headers, grafo, fake_embeddings):
    await sembrar_historial(USUARIO_A, DOCE_INTERCAMBIOS)
    await params_store.agent_params.insert_one({"_id": str(USUARIO_A), "short_term_memory_window": 4})

    respuesta = await client.post("/agent/chat", json={"message": "nuevo"}, headers=auth_headers(USUARIO_A))
    await esperar_indexado()

    assert respuesta.status_code == 200
    mensajes = grafo.recibido["messages"]
    assert len(mensajes) == 4 + 1
    assert mensajes[0] == {"role": "user", "content": "pregunta 11"}
    assert mensajes[-1] == {"role": "user", "content": "nuevo"}
    assert grafo.recibido["params"]["short_term_memory_window"] == 4


async def test_guarda_el_intercambio_y_lo_indexa_para_recuperarlo(client, auth_headers, grafo, fake_embeddings):
    respuesta = await client.post(
        "/agent/chat", json={"message": "mi consulta en el IMSS es el jueves"}, headers=auth_headers(USUARIO_A)
    )
    await esperar_indexado()

    assert respuesta.json()["response"] == "Respuesta de prueba"
    assert await short_term.get_history(USUARIO_A) == [
        {"role": "user", "content": "mi consulta en el IMSS es el jueves"},
        {"role": "assistant", "content": "Respuesta de prueba"},
    ]
    recuperados = await vector_store.search(str(USUARIO_A), "consulta en el IMSS")
    assert recuperados == ["Usuario: mi consulta en el IMSS es el jueves\nAsistente: Respuesta de prueba"]


async def test_si_falla_el_indexado_la_respuesta_no_se_rompe(client, auth_headers, grafo, monkeypatch):
    async def index_roto(user_id, text):
        raise ConnectionError("Qdrant caido")

    monkeypatch.setattr(vector_store, "index_document", index_roto)

    respuesta = await client.post("/agent/chat", json={"message": "hola"}, headers=auth_headers(USUARIO_A))
    await esperar_indexado()

    assert respuesta.status_code == 200
    assert len(await short_term.get_history(USUARIO_A)) == 2


async def test_sin_token_responde_401(client, grafo):
    respuesta = await client.post("/agent/chat", json={"message": "hola"})

    assert respuesta.status_code == 401
    assert grafo.recibido is None


async def test_token_firmado_con_otro_secreto_responde_401(client, auth_headers, grafo):
    headers = auth_headers(USUARIO_A, secreto="otro-secreto-que-no-es-el-del-servicio")
    respuesta = await client.post("/agent/chat", json={"message": "hola"}, headers=headers)

    assert respuesta.status_code == 401


async def test_history_devuelve_los_ultimos_mensajes_con_fecha(client, auth_headers):
    await sembrar_historial(USUARIO_A, DOCE_INTERCAMBIOS)

    respuesta = await client.get("/agent/history", params={"limit": 4}, headers=auth_headers(USUARIO_A))

    cuerpo = respuesta.json()
    assert [m["content"] for m in cuerpo] == ["pregunta 11", "respuesta 11", "pregunta 12", "respuesta 12"]
    assert all("created_at" in m for m in cuerpo)
