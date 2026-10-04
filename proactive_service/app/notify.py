"""Entrega de una notificacion: la guarda (con dedupe) y la manda por push."""

import logging
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.db.mongo import devices, notifications
from app.push import fcm

log = logging.getLogger("proactive.notify")


async def deliver(
    user_id: str,
    kind: str,
    title: str,
    body: str,
    dedupe_key: str,
    data: dict | None = None,
) -> bool:
    """False si ya se habia avisado lo mismo (dedupe_key repetido por usuario)."""
    doc = {
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body,
        "data": data or {},
        "dedupe_key": dedupe_key,
        "read": False,
        "push": "pending",
        "created_at": datetime.now(timezone.utc),
    }
    try:
        result = await notifications.insert_one(doc)
    except DuplicateKeyError:
        return False

    statuses: list[str] = []
    async for device in devices.find({"user_id": user_id}):
        status = await fcm.send(
            device["token"], title, body, {"kind": kind, "notification_id": str(result.inserted_id)}
        )
        if status == "invalid_token":
            await devices.delete_one({"_id": device["_id"]})
        statuses.append(status)

    if "sent" in statuses:
        push = "sent"
    elif not statuses:
        push = "no_device"
    else:
        push = statuses[0]
    await notifications.update_one({"_id": result.inserted_id}, {"$set": {"push": push}})
    return True
