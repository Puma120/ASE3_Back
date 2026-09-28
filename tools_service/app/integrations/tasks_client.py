"""Cliente de bajo nivel para Google Tasks API.

Usado por app/tools/tasks_tool.py para subdividir tareas grandes en subtareas
accionables (Cap. 3 del PDF: "metodo comprobado para evitar la paralisis por
analisis en TDAH").
"""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DEFAULT_TASKLIST = "@default"


def _service(credentials: Credentials):
    return build("tasks", "v1", credentials=credentials, cache_discovery=False)


def create_task(credentials: Credentials, title: str, notes: str = "") -> dict:
    service = _service(credentials)
    return (
        service.tasks()
        .insert(tasklist=DEFAULT_TASKLIST, body={"title": title, "notes": notes})
        .execute()
    )


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
