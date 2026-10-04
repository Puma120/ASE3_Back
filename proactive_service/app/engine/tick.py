"""Tick silencioso: cada TICK_INTERVAL_SECONDS evalua a los usuarios activos
(los que abrieron la app o registraron dispositivo/ubicacion hace poco) y
dispara los avisos que correspondan. No llama al LLM: son reglas baratas, el
LLM solo corre cuando el usuario chatea.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from app.clients import services
from app.core.config import settings
from app.db.mongo import reminders, user_state
from app.engine import rules
from app.notify import deliver

log = logging.getLogger("proactive.tick")

ACTIVE_DAYS = 14
CONCURRENCY = 5

# (user_id, event_id, start) -> (consultado_en, segundos). Evita pegarle a
# Maps en cada tick: se refresca mas seguido solo cerca de la hora de salida.
_travel_cache: dict[tuple[str, str, str], tuple[datetime, int]] = {}


async def _travel_seconds(user_id: str, event: dict, origin: str, now: datetime) -> int | None:
    key = (user_id, event["id"], event["start"])
    start = rules.parse_dt(event["start"])
    cached = _travel_cache.get(key)
    if cached:
        asked_at, seconds = cached
        time_to_leave = start - timedelta(seconds=seconds) - now
        ttl = timedelta(minutes=2 if time_to_leave <= timedelta(minutes=30) else 10)
        if now - asked_at < ttl:
            return seconds
    seconds = await services.travel_time(user_id, origin, event["location"], event["start"])
    if seconds is not None:
        _travel_cache[key] = (now, seconds)
    return seconds


def _prune_cache(now: datetime) -> None:
    for key in [k for k, (at, _) in _travel_cache.items() if now - at > timedelta(hours=6)]:
        del _travel_cache[key]


async def fire_due_reminders(now: datetime) -> int:
    """Reclama (atomico, seguro con varias replicas) y entrega los recordatorios vencidos."""
    fired = 0
    while True:
        doc = await reminders.find_one_and_update(
            {"status": "pending", "fire_at": {"$lte": now}}, {"$set": {"status": "sent"}}
        )
        if doc is None:
            return fired
        await deliver(
            doc["user_id"],
            "reminder",
            doc.get("title") or "Recordatorio",
            doc["message"],
            f"reminder:{doc['_id']}",
            {"reminder_id": str(doc["_id"])},
        )
        fired += 1


async def evaluate_user(user_id: str, now: datetime) -> int:
    """Evalua las reglas de un usuario. Devuelve cuantas notificaciones nuevas entrego."""
    try:
        user_settings = await services.get_user_settings(user_id)
    except httpx.HTTPError as exc:
        log.warning("settings de %s no disponibles: %s", user_id, exc)
        return 0
    if not user_settings.get("proactive_suggestions_enabled", True):
        return 0

    tz = ZoneInfo(user_settings.get("timezone") or "UTC")
    state = await user_state.find_one({"_id": user_id}) or {}
    location = state.get("location")
    location_fresh = bool(
        location
        and now - location["updated_at"].replace(tzinfo=timezone.utc)
        <= timedelta(minutes=settings.location_max_age_minutes)
    )
    origin = f"{location['lat']},{location['lng']}" if location_fresh else None

    alerts: list[rules.Alert] = []
    try:
        window_end = now + timedelta(minutes=settings.travel_lookahead_minutes)
        events = await services.list_events(user_id, now.isoformat(), window_end.isoformat())
        for event in events:
            if event.get("all_day"):
                continue
            seconds = None
            if event.get("location") and origin:
                seconds = await _travel_seconds(user_id, event, origin, now)
            if seconds is not None:
                alerts += rules.departure_alerts(
                    event,
                    now,
                    seconds,
                    tz,
                    timedelta(minutes=settings.prepare_lead_minutes),
                    timedelta(minutes=settings.leave_buffer_minutes),
                )
            elif (soon := rules.soon_alert(event, now, tz)) is not None:
                alerts.append(soon)

        local = now.astimezone(tz)
        work_start = user_settings.get("work_start_hour", 9)
        if work_start <= local.hour < work_start + 3:
            day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
            day_events = await services.list_events(
                user_id, day_start.isoformat(), (day_start + timedelta(days=1)).isoformat()
            )
            tasks = await services.list_tasks(user_id)
            if (brief := rules.briefing_alert(day_events, tasks, now, tz, work_start)) is not None:
                alerts.append(brief)
    except services.GoogleNotConnected:
        pass  # sin Google no hay agenda que vigilar; los recordatorios siguen funcionando
    except httpx.HTTPError as exc:
        log.warning("reglas de %s fallaron: %s", user_id, exc)

    delivered = 0
    for alert in alerts:
        if await deliver(user_id, alert.kind, alert.title, alert.body, alert.dedupe_key, alert.data):
            delivered += 1
    return delivered


async def run_tick() -> int:
    now = datetime.now(timezone.utc)
    _prune_cache(now)
    total = await fire_due_reminders(now)

    since = now - timedelta(days=ACTIVE_DAYS)
    user_ids = [doc["_id"] async for doc in user_state.find({"last_seen": {"$gte": since}}, {"_id": 1})]
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def guarded(user_id: str) -> int:
        async with semaphore:
            try:
                return await evaluate_user(user_id, now)
            except Exception:
                log.exception("tick fallo para %s", user_id)
                return 0

    total += sum(await asyncio.gather(*(guarded(u) for u in user_ids)))
    return total


async def tick_loop() -> None:
    while True:
        try:
            delivered = await run_tick()
            if delivered:
                log.info("tick: %d notificaciones entregadas", delivered)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("tick fallo")
        await asyncio.sleep(settings.tick_interval_seconds)
