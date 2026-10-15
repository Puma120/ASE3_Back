import asyncio
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import jwt

from app.core.security import (
    create_access_token,
    create_email_verification_token,
    hash_password,
    verify_email_verification_token,
    verify_password,
)
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.models.user_settings import UserSettings


class EmailTaken(Exception):
    pass


class InvalidCredentials(Exception):
    pass


class InvalidVerification(Exception):
    pass


# Hash de relleno: si el correo no existe se verifica igual contra este, para
# que el tiempo de respuesta no delate que cuentas existen.
_dummy_hash: str | None = None


async def start_registration(
    db: AsyncSession, email: str, password: str, full_name: str
) -> str:
    """Primer paso del registro con email/password (acceso alterno a Google; no
    conecta Calendar/Tasks/Gmail). No crea la cuenta: devuelve el token de
    verificacion que se manda por correo. La cuenta nace en `confirm_registration`
    solo cuando el dueno del correo abre el enlace."""
    email = email.strip().lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise EmailTaken
    hashed = await asyncio.to_thread(hash_password, password)
    return create_email_verification_token(email, hashed, full_name.strip())


async def confirm_registration(db: AsyncSession, token: str) -> None:
    """Crea la cuenta del token de verificacion. Lanza InvalidVerification si el
    token es invalido/expirado y EmailTaken si la cuenta ya existe (enlace
    abierto dos veces)."""
    try:
        data = verify_email_verification_token(token)
    except jwt.PyJWTError:
        raise InvalidVerification
    user = User(email=data["email"], full_name=data["name"], hashed_password=data["pwd"])
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise EmailTaken
    db.add(UserSettings(user_id=user.id))
    await db.commit()


async def login_with_password(db: AsyncSession, email: str, password: str) -> str:
    global _dummy_hash
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None and _dummy_hash is None:
        _dummy_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(16))
    ok = await asyncio.to_thread(
        verify_password, password, user.hashed_password if user else _dummy_hash
    )
    if user is None or not ok:
        raise InvalidCredentials
    return create_access_token(subject=str(user.id))


async def login_with_google(
    db: AsyncSession, email: str, full_name: str, tokens: dict
) -> str:
    """Encuentra o crea el usuario por email y guarda/actualiza sus tokens de
    Google (GoogleCredential), luego emite el JWT propio de sesion - mismo
    unico metodo de login (la cuenta no tiene password usable).
    """
    user = await db.scalar(select(User).where(User.email == email))
    existing = user is not None
    if user is None:
        # Cuenta creada solo via Google: no tiene password propio, se genera
        # uno aleatorio inutilizable (no se expone ni se comunica) para no
        # requerir una migracion de columna nullable en `users`.
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.flush()
        db.add(UserSettings(user_id=user.id))

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=tokens.get("expires_in", 3600)
    )
    credential = await db.scalar(
        select(GoogleCredential).where(GoogleCredential.user_id == user.id)
    )
    if credential is None:
        credential = GoogleCredential(user_id=user.id)
        db.add(credential)
        if existing:
            # Cuenta con ese correo creada antes con email/password y nunca
            # ligada a Google: Google acaba de probar que el correo es de
            # quien entra ahora, asi que se invalida la contrasena para que
            # quien se registro primero con un correo ajeno no conserve acceso.
            user.hashed_password = hash_password(secrets.token_urlsafe(32))

    credential.access_token = tokens["access_token"]
    # Google solo manda refresh_token la primera vez que el usuario consiente
    # (prompt=consent lo fuerza, pero si ya existia uno y Google no lo repite,
    # conservamos el anterior en vez de pisarlo con None).
    if tokens.get("refresh_token"):
        credential.refresh_token = tokens["refresh_token"]
    credential.scopes = tokens.get("scope", "")
    credential.expires_at = expires_at

    await db.commit()
    await db.refresh(user)
    return create_access_token(subject=str(user.id))
