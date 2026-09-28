"""Contrato (no ORM, Mongo es schemaless) del documento de la coleccion
`activity_logs` en MongoDB - historial de rutinas/tareas del usuario.

Es la fuente que agent_service.app.graph.nodes usa para el Objetivo 4 del
PDF ("analizar historial de rutinas, identificar patrones, generar
sugerencias proactivas"): cada tool que crea/completa/pospone algo aqui deja
un registro, sin logica de analisis - eso vive en agent_service.

Documento tipico:
{
    "user_id": str(uuid),
    "kind": "task_created" | "task_completed" | "task_postponed"
            | "event_scheduled" | "email_summarized" | "device_command_sent",
    "payload": {...datos especificos de la tool...},
    "created_at": datetime,
}
"""

from datetime import datetime, timezone
from typing import Any, Literal

ActivityKind = Literal[
    "task_created",
    "task_completed",
    "task_postponed",
    "event_scheduled",
    "email_summarized",
    "device_command_sent",
]


def build_activity_log(user_id: str, kind: ActivityKind, payload: dict[str, Any]) -> dict:
    return {
        "user_id": user_id,
        "kind": kind,
        "payload": payload,
        "created_at": datetime.now(timezone.utc),
    }
