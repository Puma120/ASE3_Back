"""Eventos recurrentes (rutina): RRULE semanal hasta una fecha, en la zona del usuario."""

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.integrations.calendar_client import build_recurring
from app.schemas.tools import EventCreate

MX = timezone(timedelta(hours=-6))


def test_rrule_semanal_hasta_el_fin_del_ultimo_dia():
    start = datetime(2026, 10, 26, 8, 0, tzinfo=MX)  # lunes
    first_start, first_end, rule = build_recurring(
        start, start + timedelta(hours=6), ["MO", "WE"], date(2026, 12, 15), "America/Mexico_City"
    )
    assert first_start.isoformat() == "2026-10-26T08:00:00-06:00"
    assert first_end.hour == 14
    # 23:59:59 locales del 15 de diciembre = 05:59:59 UTC del 16.
    assert rule == ["RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261216T055959Z"]


def test_la_primera_ocurrencia_se_adelanta_a_un_dia_de_la_regla():
    martes = datetime(2026, 10, 27, 8, 0, tzinfo=MX)
    first_start, _, _ = build_recurring(martes, martes + timedelta(hours=1), ["MO", "FR"], date(2026, 12, 1), "America/Mexico_City")
    assert first_start.date() == date(2026, 10, 30)  # viernes


def test_sin_weekdays_se_repite_el_dia_de_start():
    sabado = datetime(2026, 10, 31, 10, 0, tzinfo=MX)
    _, _, rule = build_recurring(sabado, sabado + timedelta(hours=1), [], date(2026, 12, 1), "America/Mexico_City")
    assert "BYDAY=SA" in rule[0]


def test_recurrente_exige_until_y_zona_valida():
    base = {"summary": "Clases", "start": "2026-10-26T08:00:00-06:00", "end": "2026-10-26T14:00:00-06:00"}
    assert EventCreate(**base).until is None  # evento simple: sin cambios
    with pytest.raises(ValidationError):
        EventCreate(**base, weekdays=["MO"])
    with pytest.raises(ValidationError):
        EventCreate(**base, until="2026-12-01")  # falta la zona
    with pytest.raises(ValidationError):
        EventCreate(**base, until="2026-12-01", timezone="Marte/Olimpo")
    with pytest.raises(ValidationError):
        EventCreate(**base, until="2026-10-01", timezone="America/Mexico_City")
    assert EventCreate(**base, weekdays=["MO"], until="2026-12-01", timezone="America/Mexico_City").until
