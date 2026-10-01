"""Login con Google (Objetivo: "Entrar con Google" identico en PWA y RN).

Flujo "authorization code" del lado del servidor (no Google Identity Services
en el cliente): el mismo OAuth Client ya configurado para Calendar/Tasks/Gmail
(ver deploy_railway_vercel.md 3.1) sirve tambien para login, pidiendo ademas
los scopes de identidad. Un solo consentimiento deja al usuario logueado y con
su cuenta de Google ya conectada para las tools.

- GET /auth/google/login?platform=web|mobile -> redirige a Google.
- GET /auth/google/callback -> Google redirige aqui con ?code=&state=; este
  endpoint intercambia el codigo, loguea/crea al usuario y redirige de vuelta
  al frontend (web: PWA_BASE_URL con #token=..., movil: deep link con
  ?token=...) para que ninguno de los dos frontends tenga que hablar
  directamente con Google.
"""

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_oauth_state_token, verify_oauth_state_token
from app.db.session import get_db
from app.services import google_oauth
from app.services.auth_service import login_with_google

router = APIRouter(prefix="/auth/google", tags=["auth"])


@router.get("/login")
async def google_login(platform: str = Query(pattern="^(web|mobile)$")) -> RedirectResponse:
    state = create_oauth_state_token(platform)
    return RedirectResponse(google_oauth.build_authorize_url(state))


@router.get("/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    try:
        platform = verify_oauth_state_token(state)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="State invalido o expirado"
        )

    tokens = await google_oauth.exchange_code(code)
    profile = await google_oauth.fetch_userinfo(tokens["access_token"])
    token = await login_with_google(
        db, email=profile["email"], full_name=profile.get("name", profile["email"]), tokens=tokens
    )

    if platform == "mobile":
        destination = f"{settings.google_oauth_mobile_scheme}://auth/callback?token={token}"
    else:
        destination = f"{settings.pwa_base_url}/#token={token}"
    return RedirectResponse(destination)
