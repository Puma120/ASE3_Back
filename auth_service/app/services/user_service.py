import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_settings import UserSettings
from app.schemas.user_settings import UserSettingsUpdate


async def get_user_or_404(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    return user


async def get_or_create_settings(db: AsyncSession, user_id: uuid.UUID) -> UserSettings:
    settings_row = await db.get(UserSettings, user_id)
    if settings_row is None:
        settings_row = UserSettings(user_id=user_id)
        db.add(settings_row)
        await db.commit()
        await db.refresh(settings_row)
    return settings_row


async def update_settings(
    db: AsyncSession, user_id: uuid.UUID, data: UserSettingsUpdate
) -> UserSettings:
    settings_row = await get_or_create_settings(db, user_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(settings_row, field, value)
    await db.commit()
    await db.refresh(settings_row)
    return settings_row
