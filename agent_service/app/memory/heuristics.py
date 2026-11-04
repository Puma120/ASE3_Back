"""Heuristicas de organizacion del usuario (Objetivo 4 del PDF).

Procesa su historial de tareas completadas y pospuestas (`activity_logs`) y
saca reglas simples y deterministas; el agente las recibe en cada turno para
proponer horarios, duraciones y divisiones de tareas que le funcionen a esa
persona. Sin LLM: es estadistica sobre datos propios del usuario.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db.mongo import activity_logs

WINDOW_DAYS = 60
MIN_COMPLETED = 4  # completadas necesarias para hablar de una franja favorita
MIN_RESCHEDULED = 3  # pospuestas con origen conocido para hablar de una franja mala
MIN_CREATED = 5  # tareas creadas para evaluar la tasa de cumplimiento
SHARE = 0.5  # una franja debe concentrar al menos esta parte de los casos
LOW_COMPLETION = 0.5
REPEATED = 2  # veces que se pospone un titulo para considerarlo "atorado"

_HEADER = (
    "Heuristicas de organizacion aprendidas del historial de tareas de este usuario (completadas y "
    "pospuestas). Aplicalas en silencio al proponer horarios, duraciones o dividir tareas; no cites "
    "estadisticas ni numeros salvo que el pregunte:"
)


def _slot(hour: int) -> str:
    if 5 <= hour < 12:
        return "manana"
    if 12 <= hour < 19:
        return "tarde"
    return "noche"


def _local(value: datetime | str, tz: ZoneInfo) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz)


def _dominant(slots: list[str], minimum: int) -> str | None:
    if len(slots) < minimum:
        return None
    slot, count = Counter(slots).most_common(1)[0]
    return slot if count / len(slots) >= SHARE else None


def derive(logs: list[dict], tz: ZoneInfo) -> list[str]:
    completed = [d for d in logs if d["kind"] == "task_completed"]
    rescheduled = [d for d in logs if d["kind"] == "task_rescheduled"]
    created = [d for d in logs if d["kind"] == "task_created"]
    rules: list[str] = []

    if slot := _dominant([_slot(_local(d["created_at"], tz).hour) for d in completed], MIN_COMPLETED):
        rules.append(f"Completa casi todo por la {slot}: ponle ahi las tareas importantes o dificiles.")

    origins = [_slot(_local(d["payload"]["from_start"], tz).hour) for d in rescheduled if d["payload"].get("from_start")]
    if slot := _dominant(origins, MIN_RESCHEDULED):
        rules.append(
            f"Suele posponer lo que agenda por la {slot}: evita cargarla con tareas importantes "
            "o usa bloques mas cortos."
        )

    titles = Counter(" ".join(d["payload"].get("title", "").split())[:60] for d in rescheduled)
    stuck = [t for t, n in titles.most_common(3) if t and n >= REPEATED]
    if stuck:
        rules.append(
            "Ha pospuesto varias veces: " + "; ".join(stuck) + ". Ofrece dividirlas en pasos pequenos "
            "o en bloques mas cortos antes de volver a agendarlas igual."
        )

    if len(created) >= MIN_CREATED and len(completed) / len(created) < LOW_COMPLETION:
        rules.append(
            "Completa menos de la mitad de lo que agenda: propon pocas tareas por dia y deja holgura entre ellas."
        )
    return rules


async def build(user_id: str, timezone_name: str | None = None) -> str:
    """Bloque de prompt con las heuristicas vigentes; vacio si aun no hay patron."""
    try:
        tz = ZoneInfo(timezone_name) if timezone_name else ZoneInfo("UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    since = datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)
    cursor = activity_logs.find(
        {
            "user_id": user_id,
            "kind": {"$in": ["task_created", "task_completed", "task_rescheduled"]},
            "created_at": {"$gte": since},
        }
    )
    rules = derive([d async for d in cursor], tz)
    return _HEADER + "\n" + "\n".join(f"- {r}" for r in rules) if rules else ""
