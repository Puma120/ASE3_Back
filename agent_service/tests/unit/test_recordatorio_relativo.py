"""'Recuerdame en 5 minutos': el LLM solo da in_minutes y el fire_at se
calcula con el reloj del servidor (el LLM redondeaba a la hora en punto)."""

import json
from datetime import datetime, timedelta, timezone

import httpx

from app.clients import tools_client
from app.graph.tool_specs import TOOL_SPECS


def _proactive_falso(monkeypatch) -> list[dict]:
    enviados: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        enviados.append(json.loads(request.content))
        return httpx.Response(201, json={"id": "r1"})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        tools_client.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    return enviados


async def test_in_minutes_se_convierte_en_fire_at(monkeypatch):
    enviados = _proactive_falso(monkeypatch)
    antes = datetime.now(timezone.utc)

    resultado = await tools_client.call_tool("create_reminder", {"message": "Hablar con Puma", "in_minutes": 5}, "t")

    assert resultado == {"id": "r1"}
    assert "in_minutes" not in enviados[0]
    fire_at = datetime.fromisoformat(enviados[0]["fire_at"])
    assert antes + timedelta(minutes=5) <= fire_at <= datetime.now(timezone.utc) + timedelta(minutes=5)


async def test_fire_at_explicito_no_se_toca(monkeypatch):
    enviados = _proactive_falso(monkeypatch)

    await tools_client.call_tool("create_reminder", {"message": "m", "fire_at": "2026-10-27T18:00:00-06:00"}, "t")

    assert enviados[0]["fire_at"] == "2026-10-27T18:00:00-06:00"


async def test_in_minutes_invalido_no_llama_al_servicio(monkeypatch):
    enviados = _proactive_falso(monkeypatch)

    for valor in (0, -3, "pronto"):
        resultado = await tools_client.call_tool("create_reminder", {"message": "m", "in_minutes": valor}, "t")
        assert "error" in resultado

    assert enviados == []


def test_la_spec_ofrece_in_minutes_y_fire_at_es_opcional():
    spec = next(s["function"] for s in TOOL_SPECS if s["function"]["name"] == "create_reminder")
    assert "in_minutes" in spec["parameters"]["properties"]
    assert spec["parameters"]["required"] == ["message"]
