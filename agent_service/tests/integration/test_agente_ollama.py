"""Extremo a extremo con el modelo local (qwen3.8): ruta /agent/chat, grafo,
memoria corta en Mongo y RAG en Qdrant reales. Demuestra que un dato que ya
salio de la ventana corta se recupera de la fuente persistente."""

import re

import pytest

from app.memory import short_term, vector_store
from tests.support.historial import USUARIO_A, indexar_historial, sembrar_historial

pytestmark = pytest.mark.ollama

DATO = (
    "Mi consulta de seguimiento en el IMSS es el jueves a las 10:30 en la UMF 20, ayúdame a no olvidarla.",
    "Anotado: **consulta en el IMSS el jueves a las 10:30** en la UMF 20. "
    "¿Te pongo un recordatorio para salir?",
)
RELLENO = [
    ("Divide mi reporte de laboratorio en pasos.", "Pasos:\n1. Resultados\n2. Gráficas\n3. Conclusiones"),
    ("Ya terminé las gráficas del reporte.", "¡Bien! Sigue con las conclusiones."),
    ("Pon el modo focus 25 minutos.", "Listo: modo focus 25 minutos."),
    ("¿Qué tengo pendiente hoy?", "Tienes dos pendientes: lavar ropa y estudiar Cálculo."),
    ("Pospón lavar ropa para mañana.", "Movido: lavar ropa, mañana a las 18:00."),
    ("Recuérdame pagar el celular el 12.", "Listo: recordatorio el 12 para pagar el celular."),
    ("Mañana entro a trabajar a las 4.", "Anotado: turno mañana a las 16:00."),
    ("Quiero dormirme a las 11:30.", "Meta: dormir a las 23:30."),
    ("Me distraje toda la tarde con el celular.", "Pasa. Retoma con un bloque corto de 15 minutos."),
    ("Pon alarma a las 6:30.", "Listo: alarma a las 6:30."),
    ("Ya entregué el reporte de laboratorio.", "¡Excelente! Una tarea menos."),
]
PREGUNTA = "¿A qué hora era mi consulta del IMSS?"
HORA = re.compile(r"10[:.]30|10 y media", re.IGNORECASE)


async def _preparar_memoria() -> None:
    intercambios = [DATO, *RELLENO]  # 12 intercambios: el dato es el mas antiguo
    await sembrar_historial(USUARIO_A, intercambios)
    await indexar_historial(USUARIO_A, intercambios)


async def _preguntar(client, auth_headers) -> str:
    respuesta = await client.post("/agent/chat", json={"message": PREGUNTA}, headers=auth_headers(USUARIO_A))
    assert respuesta.status_code == 200
    return respuesta.json()["response"]


async def test_dato_fuera_de_la_ventana_corta_se_recupera_por_rag(
    client, auth_headers, ollama_llm, ollama_embeddings
):
    await _preparar_memoria()

    ventana = await short_term.get_history(USUARIO_A)
    assert not any(HORA.search(m["content"]) for m in ventana), "el dato no debe estar en la memoria corta"
    contexto = await vector_store.search(str(USUARIO_A), PREGUNTA)
    assert any(HORA.search(f) for f in contexto), "el dato debe estar en la memoria persistente"

    respuesta = await _preguntar(client, auth_headers)

    assert HORA.search(respuesta), respuesta


async def test_sin_rag_el_agente_no_conoce_el_dato(
    client, auth_headers, ollama_llm, ollama_embeddings, monkeypatch
):
    """Control: mismo escenario sin recuperacion. Si el agente no responde la
    hora, la prueba anterior demuestra que el dato vino del RAG."""
    await _preparar_memoria()

    async def sin_rag(*args, **kwargs):
        return []

    monkeypatch.setattr(vector_store, "search", sin_rag)

    respuesta = await _preguntar(client, auth_headers)

    assert not HORA.search(respuesta), respuesta
