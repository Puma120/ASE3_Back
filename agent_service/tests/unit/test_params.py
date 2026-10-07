"""Parametros por usuario que acotan la memoria: ventana corta, top-k del RAG
y temperatura (con sus limites de validacion)."""

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.memory import params as params_store
from app.memory.params import AgentParamsUpdate
from tests.support.historial import USUARIO_A


async def test_sin_ajustes_usa_los_defaults_del_entorno():
    params = await params_store.get_params(USUARIO_A)

    assert params.short_term_memory_window == settings.short_term_memory_window
    assert params.rag_top_k == settings.rag_top_k
    assert params.llm_temperature == settings.llm_temperature


async def test_lo_guardado_se_mezcla_con_los_defaults():
    await params_store.agent_params.insert_one({"_id": str(USUARIO_A), "short_term_memory_window": 4})

    params = await params_store.get_params(USUARIO_A)

    assert params.short_term_memory_window == 4
    assert params.rag_top_k == settings.rag_top_k


async def test_update_params_persiste():
    await params_store.update_params(USUARIO_A, AgentParamsUpdate(rag_top_k=3))

    assert (await params_store.get_params(USUARIO_A)).rag_top_k == 3


@pytest.mark.parametrize(
    "cambio",
    [
        {"short_term_memory_window": 1},
        {"short_term_memory_window": 51},
        {"rag_top_k": 0},
        {"rag_top_k": 21},
        {"llm_temperature": 1.5},
    ],
)
def test_rechaza_valores_fuera_de_rango(cambio):
    with pytest.raises(ValidationError):
        AgentParamsUpdate(**cambio)


async def test_patch_params_rechaza_ventana_fuera_de_rango(client, auth_headers):
    respuesta = await client.patch(
        "/agent/params", json={"short_term_memory_window": 60}, headers=auth_headers(USUARIO_A)
    )

    assert respuesta.status_code == 422


async def test_patch_params_actualiza_la_ventana(client, auth_headers):
    respuesta = await client.patch(
        "/agent/params", json={"short_term_memory_window": 6}, headers=auth_headers(USUARIO_A)
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["short_term_memory_window"] == 6
