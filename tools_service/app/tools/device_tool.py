"""Tool: comandos hacia el dispositivo del usuario (alarmas nativas, DND).

No llama una API externa: tools_service no tiene conexion directa al
frontend, asi que esta tool solo registra la intencion en activity_logs y
devuelve un payload de comando; quien la invoca (agent_service, via
gateway) es responsable de reenviarlo a front/mobile para que ejecute la
API nativa real. Contrato de comando: {"command": str, "payload": dict}.

Ver limitacion documentada en .antigravity/project_map.md: DND/Focus control
solo disponible en Android (front/mobile), sin soporte en iOS ni en la PWA.
"""

import uuid
from datetime import datetime

from app.db.mongo import activity_logs
from app.models.activity_log import build_activity_log


async def set_alarm(user_id: uuid.UUID, time: datetime, label: str = "") -> dict:
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id), "device_command_sent", {"command": "set_alarm", "time": time.isoformat(), "label": label}
        )
    )
    return {"command": "set_alarm", "payload": {"time": time.isoformat(), "label": label}}


async def set_focus_mode(user_id: uuid.UUID, enabled: bool) -> dict:
    """Solo soportado por front/mobile en Android (Platform.OS === 'android')."""
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id), "device_command_sent", {"command": "set_focus_mode", "enabled": enabled}
        )
    )
    return {"command": "set_focus_mode", "payload": {"enabled": enabled}}
