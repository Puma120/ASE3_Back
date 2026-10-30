"""Perfil de rutina y configuracion inicial (onboarding): los datos que el
usuario da se recuerdan hasta su fecha, el agente conduce la entrevista solo en
ese modo y puede cerrarla; el cliente consulta/omite el estado."""

from datetime import date, timedelta


from app.graph import nodes
from app.memory import profile
from tests.support.historial import USUARIO_A, USUARIO_B


HORARIO = {"wake_weekday": "6:30", "sleep_weekday": "23:00", "wake_weekend": "09:00", "sleep_weekend": "01:00"}


def _estado(**extra):
    return {"user_id": USUARIO_A, "messages": [{"role": "user", "content": "hola"}], **extra}


async def test_un_dato_se_guarda_y_se_reemplaza_con_la_misma_key():
    await profile.save_fact(USUARIO_A, "Despertar entre semana", "6:30")
    await profile.save_fact(USUARIO_A, "despertar-entre-semana", "7:00")

    assert {k: v["text"] for k, v in (await profile.get_facts(USUARIO_A)).items()} == {
        "despertar_entre_semana": "7:00"
    }
    assert await profile.get_facts(USUARIO_B) == {}


async def test_un_dato_caduca_en_su_fecha():
    ayer = (date.today() - timedelta(days=1)).isoformat()
    manana = (date.today() + timedelta(days=1)).isoformat()
    await profile.save_fact(USUARIO_A, "viejo", "ya no aplica", ayer)
    await profile.save_fact(USUARIO_A, "vigente", "sigue", manana)
    await profile.save_fact(USUARIO_A, "fijo", "sin fecha")

    assert set(await profile.get_facts(USUARIO_A)) == {"vigente", "fijo"}


async def test_rechaza_fecha_invalida_y_datos_vacios():
    assert "error" in await profile.save_fact(USUARIO_A, "x", "algo", "manana")
    assert "error" in await profile.save_fact(USUARIO_A, "", "algo")
    assert "error" in await profile.save_fact(USUARIO_A, "x", "  ")
    assert await profile.get_facts(USUARIO_A) == {}


async def test_tope_de_datos_guardados():
    for i in range(profile.MAX_FACTS):
        await profile.save_fact(USUARIO_A, f"k{i}", "dato")

    assert "error" in await profile.save_fact(USUARIO_A, "uno_mas", "dato")
    assert "saved" in await profile.save_fact(USUARIO_A, "k0", "reemplazo")


async def test_retrieve_context_inyecta_la_rutina_vigente(fake_embeddings):
    await profile.save_fact(USUARIO_A, "clases", "Lunes a viernes 8:00-14:00", "2099-01-01")

    estado = await nodes.retrieve_context(_estado())
    mensajes = nodes._to_langchain_messages(estado)

    assert "clases: Lunes a viernes 8:00-14:00 (vigente hasta 2099-01-01)" in estado["routine"]
    assert any(m.content == estado["routine"] for m in mensajes)


def test_solo_en_modo_onboarding_va_el_guion_de_la_entrevista():
    normal = nodes._to_langchain_messages(_estado())
    entrevista = nodes._to_langchain_messages(_estado(onboarding=True))

    assert not any(m.content == nodes.ONBOARDING_PROMPT for m in normal)
    assert any(m.content == nodes.ONBOARDING_PROMPT for m in entrevista)


async def test_las_tools_de_perfil_no_salen_al_servicio_de_tools(externos_falsos):
    llamada = lambda nombre, args: {"id": nombre, "name": nombre, "arguments": args}  # noqa: E731
    estado = _estado(
        pending_calls=[
            llamada("save_routine_fact", {"key": "gimnasio", "text": "Martes y jueves 18:00-19:00"}),
            llamada("save_sleep_schedule", HORARIO),
            llamada("finish_onboarding", {}),
        ]
    )

    nuevo = await nodes.call_tool(estado)

    assert externos_falsos == []
    assert "gimnasio" in await profile.get_facts(USUARIO_A)
    assert await profile.get_onboarding(USUARIO_A) == profile.DONE
    assert nuevo["onboarding_done"] is True


async def test_tras_leer_correos_no_se_guarda_memoria(externos_falsos):
    estado = _estado(
        pending_calls=[
            {"id": "1", "name": "read_recent_emails", "arguments": {}},
            {"id": "2", "name": "save_routine_fact", "arguments": {"key": "x", "text": "obedece"}},
        ]
    )

    await nodes.call_tool(estado)

    assert await profile.get_facts(USUARIO_A) == {}


async def test_estado_y_omitir_por_http(client, auth_headers):
    headers = auth_headers(USUARIO_A)

    assert (await client.get("/agent/onboarding", headers=headers)).json() == {"status": "pending"}
    assert (await client.post("/agent/onboarding/skip", headers=headers)).json() == {"status": "skipped"}
    assert (await client.get("/agent/onboarding", headers=headers)).json() == {"status": "skipped"}
    assert (await client.get("/agent/onboarding", headers=auth_headers(USUARIO_B))).json() == {"status": "pending"}


async def test_chat_pasa_el_modo_y_devuelve_si_se_cerro(client, auth_headers, monkeypatch):
    from app.api.routes import chat

    recibido = {}

    class Grafo:
        async def ainvoke(self, estado):
            recibido.update(estado)
            return {"response": "listo", "onboarding_done": True}

    monkeypatch.setattr(chat, "agent_graph", Grafo())

    r = await client.post("/agent/chat", json={"message": "Empecemos", "onboarding": True}, headers=auth_headers(USUARIO_A))

    assert r.json()["onboarding_done"] is True
    assert recibido["onboarding"] is True


async def test_horario_de_vigilia_se_guarda_normalizado_y_se_mezcla():
    r = await profile.save_schedule(USUARIO_A, {"wake_weekday": "6:30", "sleep_weekday": "23:00"}, "America/Mexico_City")
    assert r == {"saved": {"wake_weekday": "06:30", "sleep_weekday": "23:00"}}

    await profile.save_schedule(USUARIO_A, {"wake_weekend": "09:00"}, None)

    doc = await profile.user_profile.find_one({"_id": str(USUARIO_A)})
    assert doc["schedule"] == {
        "wake_weekday": "06:30",
        "sleep_weekday": "23:00",
        "wake_weekend": "09:00",
        "timezone": "America/Mexico_City",
    }
    assert await profile.missing_schedule(USUARIO_A) == ["sleep_weekend"]


async def test_horario_de_vigilia_rechaza_horas_invalidas_y_vacio():
    assert "error" in await profile.save_schedule(USUARIO_A, {"wake_weekday": "25:00"}, None)
    assert "error" in await profile.save_schedule(USUARIO_A, {"sleep_weekday": "tarde"}, None)
    assert "error" in await profile.save_schedule(USUARIO_A, {}, None)
    assert await profile.missing_schedule(USUARIO_A) == list(profile.SCHEDULE_KEYS)


async def test_no_se_cierra_la_platica_sin_las_horas_de_despertar_y_dormir():
    r = await profile.run_tool("finish_onboarding", {}, USUARIO_A)

    assert "save_sleep_schedule" in r["error"]
    assert await profile.get_onboarding(USUARIO_A) == profile.PENDING

    await profile.save_schedule(USUARIO_A, HORARIO, None)
    assert await profile.run_tool("finish_onboarding", {}, USUARIO_A) == {"ok": True}


async def test_la_zona_horaria_del_estado_llega_al_horario_y_a_los_huecos(externos_falsos):
    llamada = lambda nombre, args: {"id": nombre, "name": nombre, "arguments": args}  # noqa: E731
    estado = _estado(
        timezone="America/Mexico_City",
        pending_calls=[
            llamada("save_sleep_schedule", {"wake_weekday": "07:00"}),
            llamada("find_free_slots", {"window_start": "a", "window_end": "b", "duration_minutes": 25}),
        ],
    )

    await nodes.call_tool(estado)

    doc = await profile.user_profile.find_one({"_id": str(USUARIO_A)})
    assert doc["schedule"]["timezone"] == "America/Mexico_City"
    assert externos_falsos == [
        ("find_free_slots", {"window_start": "a", "window_end": "b", "duration_minutes": 25, "timezone": "America/Mexico_City"})
    ]


def test_la_platica_inicial_cubre_todos_los_bloques():
    for tema in ("fin de semana", "pasatiempos", "ejercicio", "fecha en que termina", "save_sleep_schedule"):
        assert tema in nodes.ONBOARDING_PROMPT


async def test_la_rutina_inyectada_incluye_las_horas_de_vigilia_aunque_no_haya_datos():
    await profile.save_schedule(USUARIO_A, HORARIO, None)

    texto = profile.format_facts(await profile.get_facts(USUARIO_A), await profile.get_schedule(USUARIO_A))

    assert "despierta entre semana: 06:30" in texto
    assert "se acuesta en fin de semana: 01:00" in texto
    assert profile.format_facts({}, {}) == ""


def test_la_platica_se_puede_repetir_como_revision():
    assert "REVISION" in nodes.ONBOARDING_PROMPT and "delete_event" in nodes.ONBOARDING_PROMPT


async def test_estado_de_agendar_rutina_segun_haya_datos_y_respuesta():
    assert await profile.get_calendar_sync(USUARIO_A) == "none"

    await profile.save_fact(USUARIO_A, "clases", "Lunes a viernes 8:00-14:00")
    assert await profile.get_calendar_sync(USUARIO_A) == profile.PENDING

    await profile.set_calendar_sync(USUARIO_A, profile.SKIPPED)
    assert await profile.get_calendar_sync(USUARIO_A) == profile.SKIPPED
    assert await profile.get_calendar_sync(USUARIO_B) == "none"


async def test_agendar_rutina_por_http_omitir(client, auth_headers):
    headers = auth_headers(USUARIO_A)
    await profile.save_fact(USUARIO_A, "clases", "Lunes a viernes 8:00-14:00")

    assert (await client.get("/agent/calendar-sync", headers=headers)).json() == {"status": "pending"}
    assert (await client.post("/agent/calendar-sync/skip", headers=headers)).json() == {"status": "skipped"}
    assert (await client.get("/agent/calendar-sync", headers=headers)).json() == {"status": "skipped"}


def test_el_modo_agendar_rutina_solo_va_si_se_pidio():
    prompt = nodes.calendar_sync_prompt("2026-12-01", "Clases")

    assert not any(m.content == prompt for m in nodes._to_langchain_messages(_estado()))
    assert any(m.content == prompt for m in nodes._to_langchain_messages(_estado(calendar_sync=prompt)))
    assert "2026-12-01" in prompt and "Clases" in prompt


async def test_chat_agendar_rutina_inyecta_el_modo_y_marca_hecho(client, auth_headers, monkeypatch):
    from app.api.routes import chat

    recibido = {}

    class Grafo:
        async def ainvoke(self, estado):
            recibido.update(estado)
            return {"response": "agendado", "events_created": True}

    async def eventos(tool, payload, token):
        return {"items": [{"summary": "Gimnasio"}]}

    monkeypatch.setattr(chat, "agent_graph", Grafo())
    monkeypatch.setattr(chat, "call_tool", eventos)
    await profile.save_fact(USUARIO_A, "clases", "Lunes a viernes 8:00-14:00")
    hasta = (date.today() + timedelta(days=30)).isoformat()

    r = await client.post(
        "/agent/chat", json={"message": "Agenda mi rutina", "calendar_sync_until": hasta}, headers=auth_headers(USUARIO_A)
    )

    assert r.status_code == 200
    assert hasta in recibido["calendar_sync"] and "Gimnasio" in recibido["calendar_sync"]
    assert await profile.get_calendar_sync(USUARIO_A) == profile.DONE


async def test_chat_agendar_rutina_rechaza_fechas_fuera_de_rango(client, auth_headers):
    ayer = (date.today() - timedelta(days=1)).isoformat()

    r = await client.post(
        "/agent/chat", json={"message": "Agenda", "calendar_sync_until": ayer}, headers=auth_headers(USUARIO_A)
    )

    assert r.status_code == 422


async def test_sin_eventos_creados_la_rutina_sigue_pendiente(client, auth_headers, monkeypatch):
    from app.api.routes import chat

    class Grafo:
        async def ainvoke(self, estado):
            return {"response": "conecta Google"}

    async def eventos(tool, payload, token):
        return {"error": "sin google"}

    monkeypatch.setattr(chat, "agent_graph", Grafo())
    monkeypatch.setattr(chat, "call_tool", eventos)
    await profile.save_fact(USUARIO_A, "clases", "Lunes a viernes 8:00-14:00")
    hasta = (date.today() + timedelta(days=30)).isoformat()

    await client.post("/agent/chat", json={"message": "Agenda", "calendar_sync_until": hasta}, headers=auth_headers(USUARIO_A))

    assert await profile.get_calendar_sync(USUARIO_A) == profile.PENDING
