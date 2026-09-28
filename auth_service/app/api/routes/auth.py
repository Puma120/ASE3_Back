"""Endpoints de autenticacion: /register, /login."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    user = await register_user(db, data)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    token = await authenticate_user(db, data)
    return TokenResponse(access_token=token)
