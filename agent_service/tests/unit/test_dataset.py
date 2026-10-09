"""Validez del historial sintetico: cada respuesta esperada debe estar en los
datos, o la exactitud del agente se mediria contra algo imposible."""

import pytest

from tests.support import rag_eval

DATASET = rag_eval.cargar_dataset()
CON_RESPUESTA = [c for c in DATASET["consultas"] if c["temas"]]


def test_cada_consulta_tiene_su_esperado():
    for consulta in DATASET["consultas"]:
        if consulta["temas"]:
            assert consulta.get("esperado"), consulta["id"]
        else:
            assert consulta.get("esperado") is None, consulta["id"]


@pytest.mark.parametrize("consulta", CON_RESPUESTA, ids=[c["id"] for c in CON_RESPUESTA])
def test_lo_esperado_esta_en_el_historial_de_su_tema(consulta):
    historial = DATASET["usuarios"][consulta["usuario"]]["intercambios"]
    texto = rag_eval.normalizar(
        " ".join(rag_eval.texto_indexado(i) for i in historial if set(i["temas"]) & set(consulta["temas"]))
    )

    for grupo in consulta["esperado"]:
        assert any(rag_eval.contiene(texto, alternativa) for alternativa in grupo), grupo
