from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.engine import rules

TZ = ZoneInfo("America/Mexico_City")
START = datetime(2026, 6, 1, 23, 0, tzinfo=timezone.utc)  # 17:00 en CDMX
EVENT = {"id": "e1", "summary": "Cita", "start": START.isoformat(), "location": "Hospital"}
LEAD = timedelta(minutes=15)
BUF = timedelta(minutes=5)
TRAVEL = 15 * 60  # leave_at = 16:40 local, prepare_at = 16:25


def alerts(now):
    return rules.departure_alerts(EVENT, now, TRAVEL, TZ, LEAD, BUF)


def at(minutes_before_start):
    return START - timedelta(minutes=minutes_before_start)


def test_no_alert_when_far():
    assert alerts(at(120)) == []


def test_prepare_window():
    (a,) = alerts(at(30))  # 16:30 local
    assert a.kind == "prepare"
    assert "15 min" in a.body and "16:40" in a.body and "17:00" in a.body


def test_leave_window():
    (a,) = alerts(at(20))  # 16:40 local = leave_at
    assert a.kind == "leave"


def test_late_when_still_reachable():
    # Con colchon de 15 min la ventana de "sal ya" termina con margen de sobra.
    (a,) = rules.departure_alerts(EVENT, at(18), TRAVEL, TZ, LEAD, timedelta(minutes=15))
    assert a.kind == "late" and "Si sales ya llegas" in a.body


def test_late_when_unreachable():
    (a,) = alerts(at(10))  # faltan 10, trayecto 15
    assert a.kind == "late" and "tarde" in a.body


def test_nothing_after_start():
    assert alerts(START + timedelta(minutes=1)) == []


def test_nothing_when_already_there():
    assert rules.departure_alerts(EVENT, at(30), 60, TZ, LEAD, BUF) == []


def test_dedupe_keys_distinct_per_stage_and_stable():
    keys = {alerts(at(m))[0].dedupe_key for m in (30, 20, 10)}
    assert len(keys) == 3
    assert alerts(at(30))[0].dedupe_key == alerts(at(28))[0].dedupe_key


def test_soon_alert_window():
    assert rules.soon_alert(EVENT, at(30), TZ) is None
    assert rules.soon_alert(EVENT, at(8), TZ).kind == "soon"
    assert rules.soon_alert(EVENT, START + timedelta(minutes=1), TZ) is None


def test_briefing_only_in_morning_window_and_once_per_day():
    events = [{"summary": "Dentista", "start": START.isoformat(), "all_day": False}]
    morning = datetime(2026, 6, 1, 15, 30, tzinfo=timezone.utc)  # 09:30 local
    assert rules.briefing_alert(events, [], morning, TZ, 9).dedupe_key == "briefing:2026-06-01"
    evening = datetime(2026, 6, 2, 2, 0, tzinfo=timezone.utc)  # 20:00 local
    assert rules.briefing_alert(events, [], evening, TZ, 9) is None
    assert rules.briefing_alert([], [], morning, TZ, 9) is None
