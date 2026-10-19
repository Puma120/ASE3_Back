"""La zona horaria del dispositivo manda sobre la de Ajustes en el contexto
del agente, y la tarea con hora viaja completa hasta tools_service."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.graph import user_context
from app.graph.tool_specs import TOOL_SPECS
from app.schemas.chat import ChatMessageRequest


def _fetch(settings_tz):
    async def fetch_json(service, path, token):
        if path.endswith("/settings"):
            return {"timezone": settings_tz}
        return None

    return fetch_json


async def test_zona_del_dispositivo_manda_sobre_ajustes(monkeypatch):
    monkeypatch.setattr(user_context, "fetch_json", _fetch("America/Mexico_City"))
    texto = await user_context.build_user_context("t", "Asia/Tokyo")
    assert "zona horaria Asia/Tokyo" in texto
    ahora = datetime.now(ZoneInfo("Asia/Tokyo"))
    assert f"{ahora:%Y-%m-%dT%H}" in texto or f"{ahora:%Y-%m-%d}" in texto


async def test_sin_zona_de_dispositivo_usa_ajustes(monkeypatch):
    monkeypatch.setattr(user_context, "fetch_json", _fetch("America/Mexico_City"))
    assert "zona horaria America/Mexico_City" in await user_context.build_user_context("t")


async def test_zona_invalida_cae_a_ajustes(monkeypatch):
    monkeypatch.setattr(user_context, "fetch_json", _fetch("America/Mexico_City"))
    assert "zona horaria America/Mexico_City" in await user_context.build_user_context("t", "No/Existe")


def test_chat_request_acepta_zona_opcional():
    assert ChatMessageRequest(message="hola").timezone is None
    assert ChatMessageRequest(message="hola", timezone="America/Bogota").timezone == "America/Bogota"


def test_create_task_exige_inicio_y_fin():
    for nombre in ("create_task", "create_subtasks", "reschedule_task"):
        spec = next(t for t in TOOL_SPECS if t["function"]["name"] == nombre)
        params = spec["function"]["parameters"]
        assert {"start", "end"} <= set(params["required"])
        assert {"start", "end"} <= set(params["properties"])
