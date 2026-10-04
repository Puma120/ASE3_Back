from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

_client = AsyncIOMotorClient(settings.mongo_uri)
_db = _client[settings.mongo_db_name]

devices = _db["devices"]  # tokens de push por usuario
notifications = _db["notifications"]  # bandeja + registro de lo ya avisado (dedupe)
reminders = _db["reminders"]  # recordatorios programados (usuario o agente)
user_state = _db["user_state"]  # ultima ubicacion y actividad por usuario


async def ensure_indexes() -> None:
    await devices.create_index("token", unique=True)
    await devices.create_index("user_id")
    await notifications.create_index([("user_id", 1), ("dedupe_key", 1)], unique=True)
    await notifications.create_index([("user_id", 1), ("created_at", -1)])
    await reminders.create_index([("status", 1), ("fire_at", 1)])
    await reminders.create_index("user_id")
