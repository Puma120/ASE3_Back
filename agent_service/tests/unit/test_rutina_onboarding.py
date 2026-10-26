"""Perfil de rutina y configuracion inicial (onboarding): los datos que el
usuario da se recuerdan hasta su fecha, el agente conduce la entrevista solo en
ese modo y puede cerrarla; el cliente consulta/omite el estado."""

from datetime import date, timedelta


from app.graph import nodes
from app.memory import profile
from tests.support.historial import USUARIO_A, USUARIO_B


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
