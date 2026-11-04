"""Heuristicas de organizacion a partir del historial de tareas completadas y
pospuestas (Objetivo 4 del PDF), su inyeccion al prompt y las guardas de fecha
del agente al agendar."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.graph import nodes, user_context
from app.memory import heuristics
from tests.support.historial import USUARIO_A, USUARIO_B

MX = "America/Mexico_City"  # UTC-6 todo el ano


def _log(user, kind, hora_local, dias_atras=1, **payload):
    """Registro de activity_logs cuyo created_at cae a `hora_local` (hora de CDMX)."""
    dia = (datetime.now(timezone.utc) - timedelta(days=dias_atras)).astimezone(ZoneInfo(MX))
    momento = dia.replace(hour=hora_local, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return {"user_id": str(user), "kind": kind, "payload": payload, "created_at": momento.replace(tzinfo=None)}


async def _sembrar(mongo, docs):
    await mongo["activity_logs"].insert_many(docs)


async def test_sin_historial_no_hay_heuristicas(mongo):
    assert await heuristics.build(str(USUARIO_A), MX) == ""


async def test_franja_en_que_completa_sus_tareas(mongo):
    docs = [_log(USUARIO_A, "task_completed", h, i + 1, title=f"t{i}") for i, h in enumerate([8, 9, 10, 11, 15])]
    await _sembrar(mongo, docs)
    texto = await heuristics.build(str(USUARIO_A), MX)
    assert texto.startswith("Heuristicas de organizacion")
    assert "Completa casi todo por la manana" in texto


async def test_la_franja_usa_la_zona_del_usuario(mongo):
    # 8-11 h en CDMX son 14-17 h UTC: en UTC seria "tarde".
    await _sembrar(mongo, [_log(USUARIO_A, "task_completed", h, i + 1, title="t") for i, h in enumerate([8, 9, 10, 11])])
    assert "por la manana" in await heuristics.build(str(USUARIO_A), MX)
    assert "por la tarde" in await heuristics.build(str(USUARIO_A), "UTC")


async def test_poca_evidencia_no_genera_regla(mongo):
    await _sembrar(mongo, [_log(USUARIO_A, "task_completed", 9, 1, title="a"), _log(USUARIO_A, "task_completed", 9, 2, title="b")])
    assert await heuristics.build(str(USUARIO_A), MX) == ""


async def test_franja_en_que_pospone(mongo):
    def pospuesta(i):
        origen = (datetime.now(timezone.utc) + timedelta(days=i)).replace(hour=22, minute=0).isoformat()
        return _log(USUARIO_A, "task_rescheduled", 12, i + 1, title=f"x{i}", from_start=origen)

    await _sembrar(mongo, [pospuesta(i) for i in range(3)])
    texto = await heuristics.build(str(USUARIO_A), "UTC")
    assert "posponer lo que agenda por la noche" in texto


async def test_titulos_pospuestos_varias_veces(mongo):
    await _sembrar(
        mongo,
        [
            _log(USUARIO_A, "task_rescheduled", 12, 1, title="Declaracion de impuestos"),
            _log(USUARIO_A, "task_rescheduled", 12, 2, title="Declaracion de impuestos"),
            _log(USUARIO_A, "task_rescheduled", 12, 3, title="Una sola vez"),
        ],
    )
    texto = await heuristics.build(str(USUARIO_A), MX)
    assert "Declaracion de impuestos" in texto
    assert "Una sola vez" not in texto
    assert "dividirlas en pasos pequenos" in texto


async def test_baja_tasa_de_cumplimiento(mongo):
    docs = [_log(USUARIO_A, "task_created", 9, i + 1, title=f"t{i}") for i in range(6)]
    docs.append(_log(USUARIO_A, "task_completed", 9, 1, title="t0"))
    await _sembrar(mongo, docs)
    assert "menos de la mitad" in await heuristics.build(str(USUARIO_A), MX)


async def test_historial_viejo_o_de_otro_usuario_no_cuenta(mongo):
    viejos = [_log(USUARIO_A, "task_completed", 9, 90 + i, title="t") for i in range(5)]
    ajenos = [_log(USUARIO_B, "task_completed", 9, i + 1, title="t") for i in range(5)]
    await _sembrar(mongo, viejos + ajenos)
    assert await heuristics.build(str(USUARIO_A), MX) == ""
    assert "manana" in await heuristics.build(str(USUARIO_B), MX)


def test_las_heuristicas_entran_al_prompt():
    mensajes = nodes._to_langchain_messages(
        {"user_id": USUARIO_A, "messages": [{"role": "user", "content": "hola"}], "heuristics": "Heuristicas: X"}
    )
    assert "Heuristicas: X" in [m.content for m in mensajes]
    sin = nodes._to_langchain_messages({"user_id": USUARIO_A, "messages": [{"role": "user", "content": "hola"}]})
    assert not any("Heuristicas" in m.content for m in sin)


async def test_retrieve_context_carga_las_heuristicas(mongo, monkeypatch):
    async def contexto(*_a, **_k):
        return ""

    monkeypatch.setattr(nodes, "build_user_context", contexto)
    await _sembrar(mongo, [_log(USUARIO_A, "task_completed", h, i + 1, title="t") for i, h in enumerate([8, 9, 10, 11])])
    estado = await nodes.retrieve_context(
        {"user_id": USUARIO_A, "messages": [{"role": "user", "content": "hola"}], "timezone": MX}
    )
    assert "por la manana" in estado["heuristics"]


async def test_el_contexto_trae_el_calendario_de_los_proximos_dias(monkeypatch):
    async def fetch_json(service, path, token):
        return {"timezone": MX} if path.endswith("/settings") else None

    monkeypatch.setattr(user_context, "fetch_json", fetch_json)
    texto = await user_context.build_user_context("t", MX)
    hoy = datetime.now(ZoneInfo(MX))
    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    assert f"hoy {dias[hoy.weekday()]} {hoy.date().isoformat()}" in texto
    manana = hoy + timedelta(days=1)
    assert f"manana {dias[manana.weekday()]} {manana.date().isoformat()}" in texto
    assert (hoy + timedelta(days=13)).date().isoformat() in texto


def test_el_prompt_exige_respetar_el_dia_y_no_dar_instrucciones():
    assert "EXACTAMENTE el dia que dijo el usuario" in nodes.SYSTEM_PROMPT
    assert "Nunca le des instrucciones para que lo haga el solo" in nodes.SYSTEM_PROMPT


def _iso(delta: timedelta, tz="-06:00") -> str:
    return (datetime.now(timezone.utc) + delta).astimezone(timezone(timedelta(hours=int(tz[:3])))).isoformat()


@pytest.mark.parametrize(
    "nombre,campo",
    [
        ("create_event", "start"),
        ("create_task", "start"),
        ("create_subtasks", "start"),
        ("reschedule_task", "start"),
        ("set_alarm", "time"),
        ("create_reminder", "fire_at"),
    ],
)
def test_agendar_en_el_pasado_se_rechaza(nombre, campo):
    assert "ya paso" in nodes._stale_start(nombre, {campo: _iso(timedelta(days=-1))})


def test_agendar_hoy_o_a_futuro_pasa():
    assert nodes._stale_start("create_event", {"start": _iso(timedelta(hours=3))}) == ""
    assert nodes._stale_start("create_event", {"start": _iso(timedelta(minutes=-2))}) == ""  # tolerancia
    assert nodes._stale_start("create_reminder", {"in_minutes": 5}) == ""
    assert nodes._stale_start("list_events", {"start": _iso(timedelta(days=-1))}) == ""


def test_eventos_recurrentes_y_fechas_ambiguas_no_se_bloquean():
    pasado = _iso(timedelta(days=-3))
    assert nodes._stale_start("create_event", {"start": pasado, "weekdays": ["MO"]}) == ""
    assert nodes._stale_start("create_event", {"start": "2020-01-01T10:00:00"}) == ""  # sin offset
    assert nodes._stale_start("create_event", {"start": "no es fecha"}) == ""
