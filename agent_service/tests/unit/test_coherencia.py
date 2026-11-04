"""Prueba de coherencia del Objetivo 4, sin gastar: oraculo de los perfiles, dataset,
sensibilidad de las reglas, tope de peticiones y cableado con un LLM falso."""

from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage

from app.graph import nodes, user_context
from app.memory import heuristics, vector_store
from tests.kpi.eval_obj4 import _args, clasificar, wilson
from tests.support import coherencia_eval as ev
from tests.support.coherencia_perfiles import PERFILES, POR_CLAVE
from tests.support.rag_eval import contiene, normalizar

AHORA = datetime.now(timezone.utc)
CASOS = ev.cargar_casos()


@pytest.mark.parametrize("perfil", PERFILES, ids=[p.clave for p in PERFILES])
def test_cada_perfil_produce_exactamente_sus_reglas(perfil):
    reglas = heuristics.derive(
        [d for d in perfil.logs(AHORA) if d["created_at"] >= (AHORA - timedelta(days=heuristics.WINDOW_DAYS)).replace(tzinfo=None)],
        perfil.tz,
    )
    assert len(reglas) == len(perfil.reglas_esperadas), reglas
    for esperada in perfil.reglas_esperadas:
        assert sum(esperada in r for r in reglas) == 1, (esperada, reglas)


def test_dataset_tiene_100_casos_unicos_con_sus_cuotas():
    assert len(CASOS) == ev.LIMITE_PETICIONES
    assert len({c["id"] for c in CASOS}) == len(CASOS)
    assert len({(c["perfil"], c["mensaje"]) for c in CASOS}) == len(CASOS)
    conteo = {e: sum(c["estrato"] == e for c in CASOS) for e in ev.CUOTAS}
    assert conteo == ev.CUOTAS
    assert all(c["perfil"] in POR_CLAVE for c in CASOS)


def test_lo_requerido_de_un_chat_esta_en_ese_perfil():
    for caso in CASOS:
        chats = " ".join(f"{u} {a}" for u, a in POR_CLAVE[caso["perfil"]].chats)
        for fragmento in caso.get("fragmentos_requeridos", []):
            assert fragmento in chats, caso["id"]
        if caso["estrato"] == "dato_chat":
            for grupo in caso["esperado"]:
                assert any(contiene(normalizar(chats), alt) for alt in grupo), caso["id"]


def test_las_marcas_son_exclusivas_de_cada_perfil():
    for perfil in PERFILES:
        propios = normalizar(" ".join(
            [f"{u} {a}" for u, a in perfil.chats] + [b.titulo for b in (*perfil.eventos, *perfil.pendientes)]
        ))
        for marca in perfil.marcas:
            assert contiene(propios, marca), (perfil.clave, marca)
            for otro in PERFILES:
                if otro is not perfil:
                    assert marca not in otro.marcas


def test_extraer_horas():
    assert ev.extraer_horas("a las 22:00")[0].lecturas == (1320,)
    assert ev.extraer_horas("a las 7")[0].lecturas == (420, 1140)
    assert ev.extraer_horas("a las 7 de la noche")[0].lecturas == (1140,)
    rango = ev.extraer_horas("de 9:00 a 10:00")
    assert [h.es_fin for h in rango] == [False, True]
    assert ev.extraer_horas("de 20 a 30 minutos") == []
    assert ev.extraer_horas("el 15 de noviembre") == []


def _ejecucion(respuesta, *tools, mensaje="hola", rag=()):
    return {"ahora": AHORA.isoformat(), "mensaje": mensaje, "respuesta": respuesta, "rag_context": list(rag), "tools": list(tools)}


def _huecos(perfil):
    t = ev.ToolsSimuladas(perfil, AHORA, [])
    inicio = AHORA + timedelta(days=1)
    return {"nombre": "find_free_slots", "argumentos": {}, "resultado": {"items": t._huecos(inicio, inicio + timedelta(days=3), 30)}}


def _reglas(caso, ej):
    return {f["regla"] for f in ev.calificar(caso, ej)}


def _caso(perfil="matutino", **extra):
    return {"id": "x", "estrato": "horario", "perfil": perfil, "mensaje": "hola", **extra}


@pytest.mark.parametrize(
    "regla,caso,respuesta",
    [
        ("R1", _caso(), "Te propongo a las 13:15."),
        ("R2", _caso(franjas_validas=["manana"]), "Te conviene a las 21:00."),
        ("R2", _caso(no_afirma=["noche"]), "Rindes mejor por la noche."),
        ("R3", _caso(), "Pregúntale a Ernesto."),
        ("R4", _caso(), "La pospusiste 7 veces."),
        ("R5", _caso(), "Ya te agendé la tarea."),
        ("R6", _caso(esperado=[["b12"]]), "No recuerdo el cubículo."),
        ("R6", _caso(ofrece_dividir=True), "Va, queda para mañana."),
        ("R6", _caso(abstencion=True), "Rindes increíble."),
        ("R7", _caso(max_tareas=2), "- uno\n- dos\n- tres"),
        ("R8", _caso(), "Usé find_free_slots para eso."),
        ("R8", _caso(), "Según mi heurística te conviene."),
        ("R8", _caso(), "Completas el 70% de tus tareas."),
    ],
)
def test_una_respuesta_mala_reprueba_su_regla(regla, caso, respuesta):
    assert regla in _reglas(caso, _ejecucion(respuesta))


def test_agendar_en_franja_prohibida_y_cambiar_la_instruccion_reprueban():
    tz = POR_CLAVE["matutino"].tz
    manana = (AHORA + timedelta(days=1)).astimezone(tz).replace(hour=21, minute=0, second=0, microsecond=0)
    llamada = {"nombre": "create_task", "argumentos": {"start": manana.isoformat(), "end": (manana + timedelta(hours=1)).isoformat()}, "resultado": {"id": "t"}}
    assert "R2" in _reglas(_caso(franjas_validas=["manana"]), _ejecucion("Lista la tarea.", llamada))
    assert "R7" in _reglas(_caso(instruccion={"dia": 2, "hora": "21:00"}), _ejecucion("Lista la tarea.", llamada))
    assert "R7" not in _reglas(_caso(instruccion={"dia": 1, "hora": "21:00"}), _ejecucion("Lista la tarea.", llamada))


def test_la_sugerencia_fija_debe_coincidir_con_el_historial():
    con_patron = _caso("pospone_noches")
    assert "R9" in _reglas(con_patron, _ejecucion("Hola."))
    assert "R9" not in _reglas(con_patron, _ejecucion("Hola.\n\n" + nodes.SUGGESTION_TEXT))
    assert "R9" in _reglas(_caso("matutino"), _ejecucion("Hola.\n\n" + nodes.SUGGESTION_TEXT))


def test_la_sugerencia_fija_no_cuenta_como_ofrecer_dividir():
    caso = _caso("atorado", ofrece_dividir=True)
    assert "R6" in _reglas(caso, _ejecucion("Va.\n\n" + nodes.SUGGESTION_TEXT))


def test_una_respuesta_buena_pasa():
    perfil = POR_CLAVE["matutino"]
    ej = _ejecucion("Te propongo **mañana de 9:00 a 10:00**, por la mañana. ¿Te funciona?", _huecos(perfil))
    assert ev.calificar(_caso(franjas_validas=["manana"], afirma_franja="manana"), ej) == []


async def test_las_tools_simuladas_ofrecen_las_tres_franjas_desde_manana():
    perfil = POR_CLAVE["sin_historial"]
    tools = ev.ToolsSimuladas(perfil, AHORA, [])
    local = AHORA.astimezone(perfil.tz)
    r = await tools("find_free_slots", {"window_start": local.isoformat(), "window_end": (local + timedelta(days=2)).isoformat(), "duration_minutes": 60}, "")
    inicios = [datetime.fromisoformat(h["start"]) for h in r["items"]]
    assert {heuristics._slot(i.hour) for i in inicios} == {"manana", "tarde", "noche"}
    assert min(i.date() for i in inicios) > local.date()
    assert "error" in await tools("find_free_slots", {"window_start": "2030-01-01T09:00:00", "window_end": "2030-01-02T09:00:00"}, "")


async def test_el_tope_aborta_la_peticion_101(tmp_path):
    llamadas = []

    async def ejecutar(caso):
        llamadas.append(caso["id"])
        return {"respuesta": "ok"}

    casos = [{"id": str(i)} for i in range(101)]
    with pytest.raises(ev.PresupuestoAgotado):
        await ev.correr(casos, ev.Bitacora(tmp_path / "b.jsonl"), ejecutar)
    assert len(llamadas) == ev.LIMITE_PETICIONES


async def test_tres_errores_seguidos_cortan_la_corrida(tmp_path):
    llamadas = []

    async def ejecutar(caso):
        llamadas.append(caso["id"])
        raise RuntimeError("cuota")

    bitacora = ev.Bitacora(tmp_path / "b.jsonl")
    assert await ev.correr([{"id": str(i)} for i in range(10)], bitacora, ejecutar) == "cortada"
    assert len(llamadas) == ev.MAX_ERRORES_SEGUIDOS
    assert (tmp_path / "b.jsonl").read_text(encoding="utf-8").count('"peticion"') == ev.MAX_ERRORES_SEGUIDOS


def test_gemini_exige_confirmar_el_gasto():
    with pytest.raises(SystemExit):
        _args(["--llm", "gemini"])
    assert _args(["--llm", "gemini", "--confirmar-gasto"]).confirmar_gasto
    assert _args(["--llm", "gemini", "--verificar"]).verificar


def test_clasificacion_y_wilson():
    assert [clasificar(p) for p in (98, 97.5, 90, 89.9)] == ["Óptimo", "Aceptable", "Aceptable", "No aceptable"]
    bajo, alto = wilson(98, 100)
    assert round(bajo, 1) == 93.0 and round(alto, 1) == 99.4


async def test_ejecutar_caso_arma_el_prompt_real(monkeypatch, fake_embeddings):
    monkeypatch.setattr(user_context, "fetch_json", user_context.fetch_json)
    prompts = []

    class LLM:
        async def ainvoke(self, mensajes):
            prompts.append("\n".join(str(m.content) for m in mensajes))
            if len(prompts) == 1:
                ventana = {"window_start": AHORA.isoformat(), "window_end": (AHORA + timedelta(days=3)).isoformat(), "duration_minutes": 30}
                return AIMessage(content="", tool_calls=[{"id": "1", "name": "find_free_slots", "args": ventana}])
            return AIMessage(content="Te propongo por la mañana.")

    monkeypatch.setattr(nodes, "_get_llm", lambda *a, **k: LLM())
    await ev.sembrar_chats()
    caso = next(c for c in CASOS if c["id"] == "d02")
    ej = await ev.ejecutar_caso(caso)

    assert "Completa casi todo por la manana" in prompts[0]  # heuristica calculada del historial
    assert "Calendario de los proximos 14 dias" in prompts[0]  # contexto real
    assert "Nombre del usuario: Marta" in prompts[0]
    assert any("B12" in f for f in ej["rag_context"])  # RAG encendido y filtrado por usuario
    assert not any("Hidalgo" in f for f in ej["rag_context"])
    assert ej["tools"][0]["nombre"] == "find_free_slots" and ej["tools"][0]["resultado"]["items"]
    assert ej["respuesta"] == "Te propongo por la mañana."


async def test_si_fallan_las_heuristicas_el_turno_sigue(monkeypatch):
    async def falla(*_a, **_k):
        raise RuntimeError("mongo caido")

    monkeypatch.setattr(heuristics, "build", falla)
    monkeypatch.setattr(vector_store, "search", lambda *a, **k: _vacio())
    estado = await nodes.retrieve_context({"user_id": POR_CLAVE["matutino"].user_id, "messages": [{"role": "user", "content": "hola"}]})
    assert estado["heuristics"] == ""


async def _vacio():
    return []
