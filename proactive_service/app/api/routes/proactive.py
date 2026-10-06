"""API publica del proactive_service (via gateway: /proactive/*)."""

import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_current_user_id
from app.db.mongo import devices, notifications, reminders, user_state
from app.engine.tick import evaluate_user
from app.schemas.proactive import (
    DeviceRegister,
    DeviceUnregister,
    LocationUpdate,
    NotificationOut,
    ReminderCreate,
    ReminderOut,
    ReadRequest,
)

router = APIRouter(prefix="/proactive", tags=["proactive"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _touch(user_id: str, extra: dict | None = None) -> None:
    """Marca al usuario como activo: el tick solo evalua a quien tiene last_seen reciente."""
    await user_state.update_one(
        {"_id": user_id}, {"$set": {"last_seen": _now(), **(extra or {})}}, upsert=True
    )


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(status_code=404, detail="No encontrado") from exc


@router.post("/heartbeat", status_code=204)
async def heartbeat(user_id: uuid.UUID = Depends(get_current_user_id)) -> None:
    await _touch(str(user_id))


@router.put("/location", status_code=204)
async def update_location(
    body: LocationUpdate, user_id: uuid.UUID = Depends(get_current_user_id)
) -> None:
    await _touch(
        str(user_id),
        {"location": {"lat": body.lat, "lng": body.lng, "accuracy": body.accuracy, "updated_at": _now()}},
    )


@router.get("/location")
async def get_location(user_id: uuid.UUID = Depends(get_current_user_id)) -> dict:
    state = await user_state.find_one({"_id": str(user_id)}) or {}
    location = state.get("location")
    if not location:
        return {"location": None}
    return {
        "location": {
            "lat": location["lat"],
            "lng": location["lng"],
            "updated_at": location["updated_at"].replace(tzinfo=timezone.utc).isoformat(),
        }
    }


@router.post("/devices", status_code=204)
async def register_device(
    body: DeviceRegister, user_id: uuid.UUID = Depends(get_current_user_id)
) -> None:
    # Un token pertenece a un solo usuario: si otro lo tenia (mismo telefono,
    # otra cuenta) se reasigna.
    await devices.update_one(
        {"token": body.token},
        {
            "$set": {
                "user_id": str(user_id),
                "platform": body.platform,
                "sound": body.sound,
                "updated_at": _now(),
            }
        },
        upsert=True,
    )
    await _touch(str(user_id))


@router.delete("/devices", status_code=204)
async def unregister_device(
    body: DeviceUnregister, user_id: uuid.UUID = Depends(get_current_user_id)
) -> None:
    await devices.delete_one({"token": body.token, "user_id": str(user_id)})


@router.get("/notifications", response_model=list[NotificationOut])
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> list[NotificationOut]:
    await _touch(str(user_id))
    query: dict = {"user_id": str(user_id)}
    if unread_only:
        query["read"] = False
    cursor = notifications.find(query).sort("created_at", -1).limit(limit)
    return [
        NotificationOut(
            id=str(doc["_id"]),
            kind=doc["kind"],
            title=doc["title"],
            body=doc["body"],
            read=doc["read"],
            created_at=doc["created_at"],
            data=doc.get("data", {}),
        )
        async for doc in cursor
    ]


@router.post("/notifications/read", status_code=204)
async def mark_read(body: ReadRequest, user_id: uuid.UUID = Depends(get_current_user_id)) -> None:
    query: dict = {"user_id": str(user_id), "read": False}
    if body.ids:
        query["_id"] = {"$in": [_oid(i) for i in body.ids]}
    await notifications.update_many(query, {"$set": {"read": True}})


@router.post("/reminders", response_model=ReminderOut, status_code=201)
async def create_reminder(
    body: ReminderCreate, user_id: uuid.UUID = Depends(get_current_user_id)
) -> ReminderOut:
    fire_at = body.fire_at if body.fire_at.tzinfo else body.fire_at.replace(tzinfo=timezone.utc)
    doc = {
        "user_id": str(user_id),
        "title": body.title,
        "message": body.message,
        "fire_at": fire_at,
        "status": "pending",
        "created_at": _now(),
    }
    result = await reminders.insert_one(doc)
    await _touch(str(user_id))
    return ReminderOut(id=str(result.inserted_id), **{k: doc[k] for k in ("title", "message", "fire_at", "status")})


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(user_id: uuid.UUID = Depends(get_current_user_id)) -> list[ReminderOut]:
    cursor = reminders.find({"user_id": str(user_id), "status": "pending"}).sort("fire_at", 1)
    return [
        ReminderOut(
            id=str(doc["_id"]),
            title=doc["title"],
            message=doc["message"],
            fire_at=doc["fire_at"],
            status=doc["status"],
        )
        async for doc in cursor
    ]


@router.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(
    reminder_id: str, user_id: uuid.UUID = Depends(get_current_user_id)
) -> None:
    result = await reminders.delete_one(
        {"_id": _oid(reminder_id), "user_id": str(user_id), "status": "pending"}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")


@router.post("/tick")
async def run_tick_for_me(user_id: uuid.UUID = Depends(get_current_user_id)) -> dict:
    """Corre las reglas ahora mismo para el usuario (util para probar sin esperar al tick)."""
    await _touch(str(user_id))
    return {"delivered": await evaluate_user(str(user_id), _now())}
