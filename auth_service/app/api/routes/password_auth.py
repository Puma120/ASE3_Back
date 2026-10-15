"""Acceso con email y contrasena, alterno al login con Google.

- POST /auth/register -> crea la cuenta y devuelve el JWT de sesion.
- POST /auth/login -> valida credenciales y devuelve el JWT de sesion.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth_service import (
    EmailTaken,
    InvalidCredentials,
    login_with_password,
    register_with_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        token = await register_with_password(db, body.email, body.password, body.full_name)
    except EmailTaken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ese correo ya tiene una cuenta"
        )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        token = await login_with_password(db, body.email, body.password)
    except InvalidCredentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contrasena incorrectos"
        )
    return TokenResponse(access_token=token)
