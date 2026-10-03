import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.google_credential import GoogleCredential
from app.models.user import User
from app.models.user_settings import UserSettings


async def login_with_google(
    db: AsyncSession, email: str, full_name: str, tokens: dict
) -> str:
    """Encuentra o crea el usuario por email y guarda/actualiza sus tokens de
    Google (GoogleCredential), luego emite el JWT propio de sesion - mismo
    unico metodo de login (la cuenta no tiene password usable).
    """
    user = await db.scalar(select(User).where(User.email == email))
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
