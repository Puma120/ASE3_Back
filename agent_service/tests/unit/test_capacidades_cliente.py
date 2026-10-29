"""El agente solo recibe las tools y capacidades que el cliente puede cumplir."""

from app.graph import nodes
from app.graph.tool_specs import TOOL_SPECS, capabilities_for, specs_for


def _nombres(client: str) -> set[str]:
    return {s["function"]["name"] for s in specs_for(client)}


def test_focus_mode_solo_en_android():
    assert "set_focus_mode" in _nombres("android")
    for client in ("web", "ios", ""):
        assert "set_focus_mode" not in _nombres(client)


def test_alarma_solo_en_android_o_cliente_desconocido():
    assert "set_alarm" in _nombres("android")
    assert "set_alarm" in _nombres("")
    assert "set_alarm" not in _nombres("web")
    assert "set_alarm" not in _nombres("ios")


def test_la_pwa_declara_ubicacion_opcional():
    assert "Usar mi ubicacion en el chat" in capabilities_for("web")


def test_el_resto_de_tools_llega_a_todos_los_clientes():
    todas = {s["function"]["name"] for s in TOOL_SPECS} - {"set_alarm", "set_focus_mode"}
    for client in ("android", "web", "ios", ""):
        assert todas <= _nombres(client)


def test_el_prompt_declara_la_plataforma():
    assert "APP DE ANDROID" in capabilities_for("android")
    assert "PWA" in capabilities_for("web")
    assert "No sabes desde que app" in capabilities_for("")
    mensajes = nodes._to_langchain_messages(
        {"user_id": "u", "messages": [{"role": "user", "content": "hola"}], "client": "web"}
    )
    assert any("PWA" in m.content for m in mensajes)


def test_la_pwa_no_promete_alarmas():
    assert "crear alarmas" in capabilities_for("web").split("NO puedes")[1]


def test_create_task_y_subtasks_aceptan_focus():
    for nombre in ("create_task", "create_subtasks"):
        spec = next(s["function"] for s in TOOL_SPECS if s["function"]["name"] == nombre)
        assert spec["parameters"]["properties"]["focus"]["type"] == "boolean"
        assert "focus" not in spec["parameters"]["required"]


def test_delete_event_se_ofrece_en_todos_los_clientes_y_es_de_escritura():
    from app.clients.tools_client import TOOL_ROUTES, WRITE_TOOLS

    for client in ("android", "ios", "web", ""):
        assert "delete_event" in {s["function"]["name"] for s in specs_for(client)}
    assert "delete_event" in WRITE_TOOLS
    assert TOOL_ROUTES["delete_event"] == ("tools", "DELETE", "/tools/calendar/events/{event_id}")
