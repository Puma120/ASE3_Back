"""Calificacion automatica de las respuestas del agente (tests/support/rag_eval.py)."""

import pytest

from tests.support.rag_eval import normalizar, respuesta_correcta, se_abstiene


def test_normaliza_acentos_negritas_y_horas():
    assert normalizar("**Miércoles** a las 10.30") == "miercoles a las 10:30"


def test_normaliza_miles_con_coma():
    assert respuesta_correcta("La renta es de $4,500", [["4500"]])[0]


def test_un_numero_no_coincide_dentro_de_otro():
    assert respuesta_correcta("Tu clase es a las 19:00", [["9"]]) == (False, [["9"]])
    assert respuesta_correcta("Sales a las 9:00", [["9"]])[0]


def test_los_minutos_no_cuentan_como_numero_suelto():
    assert not respuesta_correcta("Tu cita es a las 10:30", [["30"]])[0]
    assert respuesta_correcta("Tu cita es a las 10:30", [["10:30"]])[0]


def test_las_palabras_coinciden_como_prefijo():
    assert respuesta_correcta("Decidiste avisarle al profesor", [["avis"]])[0]


def test_todos_los_grupos_son_obligatorios():
    assert respuesta_correcta("Viene el martes", [["martes"], ["9"]]) == (False, [["9"]])


def test_basta_una_alternativa_por_grupo():
    assert respuesta_correcta("Llega a la una y media", [["13:30", "una y media"]])[0]


@pytest.mark.parametrize(
    "respuesta",
    [
        "No tengo registrada ninguna cita con el dentista.",
        "No encuentro información sobre tu vuelo en tu historial.",
        "No me has dicho cuándo es el concierto.",
        "No sé cuándo es la boda de tu hermano.",
    ],
)
def test_detecta_abstencion(respuesta):
    assert se_abstiene(respuesta)


@pytest.mark.parametrize(
    "respuesta",
    [
        "Tu cita con el dentista es el jueves a las 10:30.",
        "Que no se te olvide llevar tu carnet.",
    ],
)
def test_una_respuesta_con_dato_no_es_abstencion(respuesta):
    assert not se_abstiene(respuesta)
