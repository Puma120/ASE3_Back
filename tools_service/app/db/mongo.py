"""Cliente async de MongoDB (motor) - rutinas y registros del usuario.

Una sola coleccion `activity_logs` (ver app/models/activity_log.py) basta
para todas las tools: cada una escribe su propio `kind`, y agent_service la
consulta completa para el analisis de patrones (Objetivo 4 del PDF).
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.core.config import settings

mongo_client = AsyncIOMotorClient(settings.mongo_uri)
mongo_db = mongo_client[settings.mongo_db_name]

activity_logs: AsyncIOMotorCollection = mongo_db["activity_logs"]
