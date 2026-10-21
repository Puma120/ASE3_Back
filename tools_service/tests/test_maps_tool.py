"""Lugares y horarios: la logica de apertura y el manejo de errores de Maps."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.integrations import maps_client
from app.tools import maps_tool

MX = timezone(timedelta(hours=-6))

# Oficina de lunes a viernes 8:00-14:30 (day 0 = domingo en Places).
OFFICE = [
    {"open": {"day": d, "hour": 8, "minute": 0}, "close": {"day": d, "hour": 14, "minute": 30}}
    for d in range(1, 6)
]


def test_abierto_dentro_de_horario():
    assert maps_tool.is_open_at(OFFICE, datetime(2026, 10, 20, 10, 0)) is True  # martes


def test_cerrado_despues_del_cierre():
    assert maps_tool.is_open_at(OFFICE, datetime(2026, 10, 20, 16, 0)) is False


def test_cerrado_en_domingo():
    assert maps_tool.is_open_at(OFFICE, datetime(2026, 10, 25, 10, 0)) is False


def test_horario_que_cruza_la_medianoche():
    bar = [{"open": {"day": 5, "hour": 20, "minute": 0}, "close": {"day": 6, "hour": 2, "minute": 0}}]
    assert maps_tool.is_open_at(bar, datetime(2026, 10, 24, 1, 0)) is True  # sabado 01:00
    assert maps_tool.is_open_at(bar, datetime(2026, 10, 24, 3, 0)) is False


def test_sin_cierre_es_24_horas_y_sin_datos_es_desconocido():
    assert maps_tool.is_open_at([{"open": {"day": 0, "hour": 0, "minute": 0}}], datetime(2026, 10, 20, 3)) is True
    assert maps_tool.is_open_at([], datetime(2026, 10, 20, 3)) is None


@pytest.mark.asyncio
async def test_find_places_usa_la_hora_local_del_lugar(monkeypatch):
    async def fake_search(query, lat, lng, max_results=3):
        return [
            {
                "displayName": {"text": "CFE Centro"},
                "formattedAddress": "Calle 1",
                "regularOpeningHours": {"periods": OFFICE, "weekdayDescriptions": ["lunes: 8:00-14:30"]},
                "utcOffsetMinutes": -360,
            }
        ]

    monkeypatch.setattr(maps_client, "search_places", fake_search)
    # 20:00 UTC = 14:00 en Mexico: aun abierto; 21:00 UTC = 15:00: cerrado.
    abierto = await maps_tool.find_places("cfe", at=datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc))
    cerrado = await maps_tool.find_places("cfe", at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc))
    assert abierto[0]["open_at_requested_time"] is True
    assert cerrado[0]["open_at_requested_time"] is False
    assert cerrado[0]["name"] == "CFE Centro"


@pytest.mark.asyncio
async def test_places_denegado_levanta_error_claro(monkeypatch):
    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def post(self, *a, **k):
            return httpx.Response(403, json={"error": {"message": "Places API (New) has not been used"}})

    monkeypatch.setattr(maps_client.httpx, "AsyncClient", FakeClient)
    with pytest.raises(ValueError, match="Places API"):
        await maps_client.search_places("cfe")


@pytest.mark.asyncio
async def test_travel_time_parsea_routes_api(monkeypatch):
    sent = {}

    class FakeClient:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def post(self, url, json, headers):
            sent.update(json)
            return httpx.Response(200, json={"routes": [{"duration": "1260s"}]})

    monkeypatch.setattr(maps_client.httpx, "AsyncClient", FakeClient)
    result = await maps_client.get_travel_time("19.43,-99.13", "Av. Reforma 1, CDMX")
    assert result == timedelta(seconds=1260)
    assert sent["origin"]["location"]["latLng"]["latitude"] == 19.43
    assert sent["destination"] == {"address": "Av. Reforma 1, CDMX"}
    assert "departureTime" not in sent
