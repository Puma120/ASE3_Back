"""Memoria a corto plazo: solo los ultimos N mensajes del usuario llegan al
prompt; lo anterior queda para las fuentes persistentes (Qdrant)."""

from datetime import timedelta

from app.core.config import settings
from app.memory import short_term
from tests.support.historial import USUARIO_A, USUARIO_B, sembrar_historial

DOCE_INTERCAMBIOS = [(f"pregunta {i}", f"respuesta {i}") for i in range(1, 13)]


async def test_la_ventana_retiene_solo_los_ultimos_mensajes():
    await sembrar_historial(USUARIO_A, DOCE_INTERCAMBIOS)

    historial = await short_term.get_history(USUARIO_A, window=10)

    assert len(historial) == 10
    # 10 mensajes = los ultimos 5 intercambios (8 a 12), en orden cronologico.
    assert historial[0] == {"role": "user", "content": "pregunta 8"}
    assert historial[-1] == {"role": "assistant", "content": "respuesta 12"}
    assert [m["role"] for m in historial] == ["user", "assistant"] * 5
    assert not any(m["content"] in ("pregunta 1", "respuesta 1") for m in historial)


async def test_sin_ventana_usa_la_configurada():
    await sembrar_historial(USUARIO_A, DOCE_INTERCAMBIOS)

    historial = await short_term.get_history(USUARIO_A)

    assert len(historial) == settings.short_term_memory_window == 10


async def test_historial_mas_corto_que_la_ventana_se_devuelve_completo():
    await sembrar_historial(USUARIO_A, DOCE_INTERCAMBIOS[:2])

    assert len(await short_term.get_history(USUARIO_A, window=10)) == 4


async def test_no_mezcla_el_historial_de_otro_usuario():
    await sembrar_historial(USUARIO_A, [("hola soy A", "hola A")])
    await sembrar_historial(USUARIO_B, [("hola soy B", "hola B")])

    historial = await short_term.get_history(USUARIO_A)

    assert [m["content"] for m in historial] == ["hola soy A", "hola A"]


async def test_append_exchange_guarda_usuario_y_luego_asistente():
    await short_term.append_exchange(USUARIO_A, "agenda mi cita", "Listo, la agende")

    historial = await short_term.get_history(USUARIO_A)

    assert historial == [
        {"role": "user", "content": "agenda mi cita"},
        {"role": "assistant", "content": "Listo, la agende"},
    ]


async def test_ensure_indexes_crea_indice_de_retencion():
    await short_term.ensure_indexes()

    indices = await short_term.chat_history.index_information()

    ttl = [i for i in indices.values() if "expireAfterSeconds" in i]
    assert ttl and ttl[0]["expireAfterSeconds"] == timedelta(days=short_term.RETENTION_DAYS).total_seconds()
