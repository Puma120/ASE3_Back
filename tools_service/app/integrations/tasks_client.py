"""Cliente de bajo nivel para Google Tasks API.

Usado por app/tools/tasks_tool.py para subdividir tareas grandes en subtareas
accionables (Cap. 3 del PDF: "metodo comprobado para evitar la paralisis por
analisis en TDAH").
"""

from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DEFAULT_TASKLIST = "@default"


def _service(credentials: Credentials):
    return build("tasks", "v1", credentials=credentials, cache_discovery=False)


def create_task(credentials: Credentials, title: str, notes: str = "", due: datetime | None = None) -> dict:
    body = {"title": title, "notes": notes}
    if due is not None:
        # Google Tasks solo guarda la fecha de `due` (descarta la hora): se manda el
        # dia local del usuario a medianoche UTC para que no se corra de dia.
        body["due"] = f"{due.date().isoformat()}T00:00:00.000Z"
    return _service(credentials).tasks().insert(tasklist=DEFAULT_TASKLIST, body=body).execute()


def create_subtasks(credentials: Credentials, parent_title: str, subtasks: list[str]) -> list[dict]:
    """Crea la tarea padre y una tarea por cada subtarea (Google Tasks no
    soporta jerarquia nativa via API publica de forma sencilla, asi que cada
    subtarea queda como item propio con el titulo del padre como prefijo,
    para mantenerlas agrupables visualmente en el cliente)."""
    service = _service(credentials)
    parent = service.tasks().insert(
        tasklist=DEFAULT_TASKLIST, body={"title": parent_title}
    ).execute()
    created = [parent]
    for subtask_title in subtasks:
        created.append(
            service.tasks()
            .insert(
                tasklist=DEFAULT_TASKLIST,
                body={"title": f"{parent_title} - {subtask_title}"},
            )
            .execute()
        )
    return created


def list_pending_tasks(credentials: Credentials) -> list[dict]:
    result = (
        _service(credentials)
        .tasks()
        .list(tasklist=DEFAULT_TASKLIST, showCompleted=False, maxResults=50)
        .execute()
    )
    return result.get("items", [])


def complete_task(credentials: Credentials, task_id: str) -> dict:
    return (
        _service(credentials)
        .tasks()
        .patch(tasklist=DEFAULT_TASKLIST, task=task_id, body={"status": "completed"})
        .execute()
    )


def reopen_task(credentials: Credentials, task_id: str) -> dict:
    """Deshace complete_task: la tarea vuelve a pendientes."""
    return (
        _service(credentials)
        .tasks()
        .patch(
            tasklist=DEFAULT_TASKLIST,
            task=task_id,
            body={"status": "needsAction", "completed": None},
        )
        .execute()
    )
