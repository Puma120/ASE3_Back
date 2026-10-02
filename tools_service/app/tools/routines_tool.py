"""Resumen de rutinas y racha a partir de `activity_logs` (Objetivo 4 del PDF).

Racha = dias consecutivos (hasta hoy, o hasta ayer si hoy aun no hay actividad)
con al menos un registro de actividad productiva.
"""

import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from app.db.mongo import activity_logs

PRODUCTIVE_KINDS = ["task_created", "task_completed", "event_scheduled"]
WEEK_DAYS = 7
LOOKBACK_DAYS = 60


def _streak(active_days: set[date], today: date) -> int:
    cursor = today if today in active_days else today - timedelta(days=1)
    streak = 0
    while cursor in active_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def routines_summary(user_id: uuid.UUID) -> dict:
    today = datetime.now(timezone.utc).date()
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    cursor = activity_logs.find(
        {"user_id": str(user_id), "kind": {"$in": PRODUCTIVE_KINDS}, "created_at": {"$gte": since}}
    )
    per_day: Counter[date] = Counter()
    kinds: Counter[str] = Counter()
    week_start = today - timedelta(days=WEEK_DAYS - 1)
    async for doc in cursor:
        day = doc["created_at"].date()
        per_day[day] += 1
        if day >= week_start:
            kinds[doc["kind"]] += 1

    return {
        "streak_days": _streak(set(per_day), today),
        "week": [
            {"date": (day := week_start + timedelta(days=i)).isoformat(), "count": per_day.get(day, 0)}
            for i in range(WEEK_DAYS)
        ],
        "completed_week": kinds.get("task_completed", 0),
        "created_week": kinds.get("task_created", 0),
        "scheduled_week": kinds.get("event_scheduled", 0),
    }
