"""Cliente async de MongoDB (motor) - lectura de `activity_logs`, la misma
coleccion que tools_service escribe (ver app/graph/nodes.py:
generate_proactive_suggestion, Objetivo 4 del PDF). agent_service solo lee.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.core.config import settings

mongo_client = AsyncIOMotorClient(settings.mongo_uri)
mongo_db = mongo_client[settings.mongo_db_name]

activity_logs: AsyncIOMotorCollection = mongo_db["activity_logs"]
