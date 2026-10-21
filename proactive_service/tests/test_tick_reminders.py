"""fire_due_reminders: una entrega fallida no pierde el recordatorio ni aborta el tick."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.engine import tick

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


class FakeReminders:
    def __init__(self, docs):
        self.docs = docs

    async def find_one_and_update(self, query, update):
        for d in self.docs:
            if d["status"] == "pending" and d["fire_at"] <= query["fire_at"]["$lte"]:
                d.update(update["$set"])
                return d
        return None

    async def update_one(self, query, update):
        doc = next(d for d in self.docs if d["_id"] == query["_id"])
        doc.update(update.get("$set", {}))
        for key, inc in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + inc


def _doc(i, **extra):
    return {"_id": i, "user_id": "u", "message": "m", "status": "pending", "fire_at": NOW - timedelta(minutes=1), **extra}


@pytest.fixture
def env(monkeypatch):
    docs = [_doc(1), _doc(2)]
    monkeypatch.setattr(tick, "reminders", FakeReminders(docs))
    return docs


def test_entrega_fallida_vuelve_a_pendiente_y_sigue_con_los_demas(env, monkeypatch):
    async def deliver(user_id, kind, title, body, key, data):
        if data["reminder_id"] == "1":
            raise RuntimeError("fcm caido")

    monkeypatch.setattr(tick, "deliver", deliver)

    assert asyncio.run(tick.fire_due_reminders(NOW)) == 1
    assert env[0]["status"] == "pending" and env[0]["attempts"] == 1 and env[0]["fire_at"] > NOW
    assert env[1]["status"] == "sent"


def test_tras_el_maximo_de_intentos_se_marca_fallido(env, monkeypatch):
    env[0]["attempts"] = tick.REMINDER_MAX_ATTEMPTS - 1

    async def deliver(*args):
        raise RuntimeError("fcm caido")

    monkeypatch.setattr(tick, "deliver", deliver)
    asyncio.run(tick.fire_due_reminders(NOW))
    assert env[0]["status"] == "failed"
