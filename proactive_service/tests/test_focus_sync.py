"""sync_focus: No molestar se prende al entrar en una tarea de enfoque y se apaga al salir."""

import pytest

from app.engine import tick

pytestmark = pytest.mark.asyncio


class FakeState:
    def __init__(self, doc=None):
        self.doc = doc

    async def find_one(self, _q):
        return self.doc

    async def update_one(self, _q, update, upsert=False):
        self.doc = {**(self.doc or {}), **update["$set"]}


class FakeDevices:
    def __init__(self, docs):
        self.docs = docs
        self.deleted = []

    def find(self, _q):
        docs = self.docs

        class Cursor:
            def __aiter__(self):
                async def gen():
                    for d in docs:
                        yield d

                return gen()

        return Cursor()

    async def delete_one(self, q):
        self.deleted.append(q["_id"])


@pytest.fixture
def env(monkeypatch):
    calls = {"sent": [], "active": [{"task_id": "t"}], "status": "sent"}
    state = FakeState()
    monkeypatch.setattr(tick, "user_state", state)
    monkeypatch.setattr(tick, "devices", FakeDevices([{"_id": 1, "token": "tok"}]))

    async def focus_now(_uid):
        return calls["active"]

    async def send_focus(token, enabled):
        calls["sent"].append(enabled)
        return calls["status"]

    monkeypatch.setattr(tick.services, "focus_now", focus_now)
    monkeypatch.setattr(tick.fcm, "send_focus", send_focus)
    return calls, state


async def test_prende_una_sola_vez_y_apaga_al_terminar(env):
    calls, state = env
    cfg = {"focus_mode_enabled": True}
    await tick.sync_focus("u", cfg)
    await tick.sync_focus("u", cfg)
    assert calls["sent"] == [True] and state.doc["focus_on"] is True
    calls["active"] = []
    await tick.sync_focus("u", cfg)
    assert calls["sent"] == [True, False] and state.doc["focus_on"] is False


async def test_sin_el_interruptor_de_ajustes_no_hace_nada(env):
    calls, state = env
    await tick.sync_focus("u", {"focus_mode_enabled": False})
    assert calls["sent"] == [] and state.doc is None


async def test_apagar_el_interruptor_con_enfoque_activo_lo_apaga(env):
    calls, state = env
    state.doc = {"focus_on": True}
    await tick.sync_focus("u", {"focus_mode_enabled": False})
    assert calls["sent"] == [False]


async def test_si_el_push_falla_se_reintenta_en_el_siguiente_tick(env):
    calls, state = env
    calls["status"] = "error"
    await tick.sync_focus("u", {"focus_mode_enabled": True})
    assert state.doc is None
    calls["status"] = "sent"
    await tick.sync_focus("u", {"focus_mode_enabled": True})
    assert state.doc["focus_on"] is True
