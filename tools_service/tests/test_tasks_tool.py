"""Tareas contra calendario: creacion con evento, vencimiento y reagendado.

Google y Mongo se sustituyen por fakes en memoria; lo que se prueba es la
logica de app/tools/tasks_tool.py.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from googleapiclient.errors import HttpError

from app.tools import tasks_tool

USER = uuid.uuid4()
UTC = timezone.utc


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []

    def _match(self, doc, query):
        for key, cond in query.items():
            value = doc.get(key)
            if isinstance(cond, dict):
                if "$lte" in cond and not value <= cond["$lte"]:
                    return False
            elif value != cond:
                return False
        return True

    async def update_one(self, query, update, upsert=False):
        doc = next((d for d in self.docs if self._match(d, query)), None)
        if doc is None and upsert:
            doc = {k: v for k, v in query.items() if not isinstance(v, dict)}
            doc.update(update.get("$setOnInsert", {}))
            doc["_id"] = len(self.docs) + 1
            self.docs.append(doc)
        if doc is not None:
            doc.update(update.get("$set", {}))

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def find_one(self, query):
        return next((d for d in self.docs if self._match(d, query)), None)

    def find(self, query):
        found = [d for d in self.docs if self._match(d, query)]

        class Cursor:
            def limit(self, _n):
                return self

            def __aiter__(self):
                async def gen():
                    for d in found:
                        yield d

                return gen()

        return Cursor()


class FakeGoogle:
    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.events: dict[str, dict] = {}
        self.dead_events: set[str] = set()

    def create_task(self, _c, title, notes="", due=None):
        task = {"id": f"t{len(self.tasks) + 1}", "title": title, "notes": notes, "status": "needsAction"}
        self.tasks[task["id"]] = task
        return task

    def get_task(self, _c, task_id):
        if task_id not in self.tasks:
            raise HttpError(type("R", (), {"status": 404, "reason": "nf"})(), b"")
        return self.tasks[task_id]

    def set_due(self, _c, task_id, due, notes=None):
        if notes is not None:
            self.tasks[task_id]["notes"] = notes
        return self.tasks[task_id]

    def create_event(self, _c, summary, start, end, description=""):
        event = {"id": f"e{len(self.events) + 1}", "summary": summary, "start": start, "end": end}
        self.events[event["id"]] = event
        return event

    def move_event(self, _c, event_id, start, end):
        if event_id in self.dead_events:
            raise HttpError(type("R", (), {"status": 404, "reason": "nf"})(), b"")
        self.events[event_id].update(start=start, end=end)
        return self.events[event_id]


@pytest.fixture
def env(monkeypatch):
    scheduled, logs, google = FakeCollection(), FakeCollection(), FakeGoogle()
    monkeypatch.setattr(tasks_tool, "scheduled_tasks", scheduled)
    monkeypatch.setattr(tasks_tool, "activity_logs", logs)

    async def creds(_db, _uid):
        return object()

    monkeypatch.setattr(tasks_tool, "get_user_credentials", creds)
    for name in ("create_task", "get_task", "set_due"):
        monkeypatch.setattr(tasks_tool.tasks_client, name, getattr(google, name))
    for name in ("create_event", "move_event"):
        monkeypatch.setattr(tasks_tool.calendar_client, name, getattr(google, name))
    return scheduled, google


def _window(hours_from_now: float, length_h: float = 1):
    start = datetime.now(UTC) + timedelta(hours=hours_from_now)
    return start, start + timedelta(hours=length_h)


async def test_create_task_bloquea_calendario_y_registra(env):
    scheduled, google = env
    start, end = _window(1)
    result = await tasks_tool.create_task(None, USER, "Informe", "", start, end)

    assert result["event_id"] == "e1" and google.events["e1"]["summary"] == "Tarea: Informe"
    assert "Inicio:" in google.tasks["t1"]["notes"] and "Fin:" in google.tasks["t1"]["notes"]
    (doc,) = scheduled.docs
    assert doc["status"] == "active" and doc["task_id"] == "t1" and doc["end"] == end.astimezone(UTC)


async def test_create_task_sin_ventana_falla(env):
    with pytest.raises(ValueError):
        await tasks_tool.create_task(None, USER, "Informe")


async def test_overdue_solo_devuelve_vencidas_pendientes(env):
    scheduled, google = env
    pasada = _window(-3)
    futura = _window(2)
    await tasks_tool.create_task(None, USER, "Vencida", "", *pasada)
    await tasks_tool.create_task(None, USER, "Futura", "", *futura)
    await tasks_tool.create_task(None, USER, "Hecha", "", *pasada)
    google.tasks["t3"]["status"] = "completed"

    overdue = await tasks_tool.overdue_tasks(None, USER)

    assert [t["title"] for t in overdue] == ["Vencida"]
    estados = {d["task_id"]: d["status"] for d in scheduled.docs}
    assert estados == {"t1": "active", "t2": "active", "t3": "done"}  # la hecha se cierra sola


async def test_overdue_cierra_las_borradas_en_google(env):
    scheduled, google = env
    await tasks_tool.create_task(None, USER, "Borrada", "", *_window(-3))
    del google.tasks["t1"]

    assert await tasks_tool.overdue_tasks(None, USER) == []
    assert scheduled.docs[0]["status"] == "gone"


async def test_reschedule_mueve_evento_y_deja_de_estar_vencida(env):
    scheduled, google = env
    await tasks_tool.create_task(None, USER, "Informe", "", *_window(-3))
    start, end = _window(5)

    result = await tasks_tool.reschedule_task(None, USER, "t1", start, end)

    assert result["id"] == "t1" and google.events["e1"]["start"] == start
    assert google.tasks["t1"]["notes"].count("Inicio:") == 1  # no acumula lineas
    assert await tasks_tool.overdue_tasks(None, USER) == []


async def test_reschedule_recrea_evento_borrado_por_el_usuario(env):
    scheduled, google = env
    await tasks_tool.create_task(None, USER, "Informe", "", *_window(-3))
    google.dead_events.add("e1")

    await tasks_tool.reschedule_task(None, USER, "t1", *_window(4))

    assert scheduled.docs[0]["event_id"] == "e2"


async def test_complete_cierra_el_seguimiento(env, monkeypatch):
    scheduled, google = env
    await tasks_tool.create_task(None, USER, "Informe", "", *_window(-3))
    monkeypatch.setattr(
        tasks_tool.tasks_client, "complete_task", lambda _c, tid: {**google.tasks[tid], "status": "completed"}
    )

    await tasks_tool.complete_task(None, USER, "t1")

    assert scheduled.docs[0]["status"] == "done"
