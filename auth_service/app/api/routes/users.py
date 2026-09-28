"""Endpoints de perfil/configuracion de usuario: /users/me, /users/me/settings."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user_id
from app.db.session import get_db
from app.schemas.auth import UserResponse
from app.schemas.user_settings import UserSettingsResponse, UserSettingsUpdate
from app.services.user_service import get_or_create_settings, get_user_or_404, update_settings

router = APIRouter(prefix="/auth/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def read_me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    user = await get_user_or_404(db, user_id)
    return UserResponse.model_validate(user)


@router.get("/me/settings", response_model=UserSettingsResponse)
async def read_settings(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    settings_row = await get_or_create_settings(db, user_id)
    return UserSettingsResponse.model_validate(settings_row)


@router.patch("/me/settings", response_model=UserSettingsResponse)
async def patch_settings(
    data: UserSettingsUpdate,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    settings_row = await update_settings(db, user_id, data)
    return UserSettingsResponse.model_validate(settings_row)
