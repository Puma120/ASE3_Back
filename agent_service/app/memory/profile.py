"""Perfil de rutina: datos que el usuario da una vez (hora de despertar, de
clases o trabajo, horas ocupadas...) y que el agente debe recordar el tiempo
que el diga. Vive en Mongo (`user_profile`) y se inyecta completo en cada
prompt: a diferencia del RAG, no depende de la similitud con el mensaje ni se
purga por antiguedad. Cada dato caduca en su fecha `until`.

Tambien guarda si la configuracion inicial (onboarding) esta hecha u omitida.
"""

import re
from datetime import date, datetime, timezone
from uuid import UUID

from app.db.mongo import user_profile

MAX_FACTS = 40
MAX_TEXT = 300

PENDING, DONE, SKIPPED = "pending", "done", "skipped"

# Tools que no salen a otro servicio: leen/escriben el perfil del propio agente.
LOCAL_TOOLS = {"save_routine_fact", "save_sleep_schedule", "finish_onboarding"}

# Horas de vigilia: tools_service las lee de `user_profile.schedule` para no ofrecer huecos de madrugada.
SCHEDULE_KEYS = ("wake_weekday", "sleep_weekday", "wake_weekend", "sleep_weekend")
_HM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _key(raw: str) -> str:
    """Clave estable y valida como campo de Mongo (sin puntos ni $)."""
    return re.sub(r"[^a-z0-9]+", "_", str(raw).lower()).strip("_")[:40]


async def save_fact(user_id: UUID, key: str, text: str, until: str | None = None) -> dict:
    key, text = _key(key), str(text).strip()[:MAX_TEXT]
    if not key or not text:
        return {"error": "key y text son obligatorios"}
    if until:
        try:
            date.fromisoformat(until)
        except ValueError:
            return {"error": "until debe ser una fecha YYYY-MM-DD"}
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    facts = doc.get("facts", {})
    if key not in facts and len(facts) >= MAX_FACTS:
        return {"error": f"Ya hay {MAX_FACTS} datos guardados; reemplaza uno existente usando su key"}
    await user_profile.update_one(
        {"_id": str(user_id)},
        {"$set": {f"facts.{key}": {"text": text, "until": until or None, "updated_at": datetime.now(timezone.utc)}}},
        upsert=True,
    )
    return {"saved": key, "until": until or None}


async def save_schedule(user_id: UUID, values: dict, tz_name: str | None) -> dict:
    """Guarda (mezclando con lo previo) a que hora despierta y duerme el usuario."""
    clean = {}
    for key in SCHEDULE_KEYS:
        raw = values.get(key)
        if raw in (None, ""):
            continue
        m = _HM.match(str(raw).strip())
        if not m:
            return {"error": f"{key} debe ser una hora HH:MM de 24 h"}
        clean[key] = f"{int(m[1]):02d}:{m[2]}"
    if not clean:
        return {"error": "Indica al menos una hora (wake_weekday, sleep_weekday, wake_weekend, sleep_weekend)"}
    update = {f"schedule.{k}": v for k, v in clean.items()}
    if tz_name:
        update["schedule.timezone"] = tz_name
    await user_profile.update_one({"_id": str(user_id)}, {"$set": update}, upsert=True)
    return {"saved": clean}


async def missing_schedule(user_id: UUID) -> list[str]:
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    schedule = doc.get("schedule", {})
    return [k for k in SCHEDULE_KEYS if k not in schedule]


async def get_facts(user_id: UUID) -> dict[str, dict]:
    """Datos vigentes (los caducados no se devuelven)."""
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    today = date.today().isoformat()
    return {k: v for k, v in doc.get("facts", {}).items() if not v.get("until") or v["until"] >= today}


async def get_schedule(user_id: UUID) -> dict:
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    return doc.get("schedule") or {}


def format_facts(facts: dict[str, dict], schedule: dict | None = None) -> str:
    lines = [
        f"- {k}: {v['text']}" + (f" (vigente hasta {v['until']})" if v.get("until") else "")
        for k, v in facts.items()
    ]
    labels = {
        "wake_weekday": "despierta entre semana",
        "sleep_weekday": "se acuesta entre semana",
        "wake_weekend": "despierta en fin de semana",
        "sleep_weekend": "se acuesta en fin de semana",
    }
    lines += [f"- {label}: {schedule[k]}" for k, label in labels.items() if schedule and schedule.get(k)]
    if not lines:
        return ""
    return (
        "Rutina y datos fijos que el usuario te dio (vigentes). Dalos por sabidos: no se los vuelvas a "
        "preguntar, y no agendes nada proactivo encima de sus horas ocupadas:\n" + "\n".join(lines)
    )


async def get_onboarding(user_id: UUID) -> str:
    doc = await user_profile.find_one({"_id": str(user_id)}) or {}
    return doc.get("onboarding", PENDING)


async def set_onboarding(user_id: UUID, status: str) -> None:
    await user_profile.update_one({"_id": str(user_id)}, {"$set": {"onboarding": status}}, upsert=True)


async def run_tool(name: str, arguments: dict, user_id: UUID, tz_name: str | None = None) -> dict:
    if name == "save_sleep_schedule":
        return await save_schedule(user_id, arguments, tz_name)
    if name == "save_routine_fact":
        return await save_fact(user_id, arguments.get("key", ""), arguments.get("text", ""), arguments.get("until"))
    if name == "finish_onboarding":
        missing = await missing_schedule(user_id)
        if missing:
            return {"error": "Aun falta guardar con save_sleep_schedule: " + ", ".join(missing)}
        await set_onboarding(user_id, DONE)
        return {"ok": True}
    return {"error": f"Tool desconocida: {name}"}
