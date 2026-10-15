"""Acceso con email y contrasena, alterno al login con Google.

- POST /auth/register -> valida y manda el correo de verificacion (202); la
  cuenta no existe hasta confirmar.
- GET /auth/verify-email?token= -> enlace del correo: crea la cuenta.
- POST /auth/login -> valida credenciales y devuelve el JWT de sesion.

Login y registro tienen limite de intentos (core/rate_limit.py).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import settings
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth_service import (
    EmailTaken,
    InvalidCredentials,
    InvalidVerification,
    confirm_registration,
    login_with_password,
    start_registration,
)
from app.services.mailer import MailNotConfigured, MailSendFailed, send_verification_email

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_WINDOW = 15 * 60
LOGIN_MAX_PER_EMAIL_IP = 5  # fallos por (correo, IP)
LOGIN_MAX_PER_IP = 30  # fallos por IP (barrido de muchos correos)
REGISTER_WINDOW = 60 * 60
REGISTER_MAX_PER_IP = 5  # cada registro manda un correo


def _client_ip(request: Request) -> str:
    # El gateway reenvia X-Forwarded-For tal cual; el ultimo valor lo agrega el
    # borde de Railway, los anteriores los controla el cliente (falsificables).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _too_many(wait: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Demasiados intentos. Intenta de nuevo mas tarde.",
        headers={"Retry-After": str(wait)},
    )


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
async def register(
    body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    ip_key = f"reg:{_client_ip(request)}"
    wait = rate_limit.retry_after(ip_key, REGISTER_MAX_PER_IP, REGISTER_WINDOW)
    if wait:
        raise _too_many(wait)
    if not settings.resend_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El registro con correo no esta disponible por ahora",
        )
    try:
        token = await start_registration(db, body.email, body.password, body.full_name)
    except EmailTaken:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Ese correo ya tiene una cuenta"
        )
    rate_limit.record(ip_key, REGISTER_WINDOW)
    link = f"{settings.public_base_url}/auth/verify-email?token={token}"
    try:
        await send_verification_email(body.email.strip().lower(), body.full_name, link)
    except (MailNotConfigured, MailSendFailed):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo enviar el correo de verificacion. Intenta de nuevo.",
        )
    return {"detail": "Te enviamos un correo para confirmar tu cuenta"}


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await confirm_registration(db, token)
    except InvalidVerification:
        return _page("Enlace invalido o vencido", "Vuelve a registrarte desde la app.", 400)
    except EmailTaken:
        return _page("Tu cuenta ya estaba activa", "Ya puedes iniciar sesion desde la app.")
    return _page("Correo confirmado", "Tu cuenta esta activa. Vuelve a la app e inicia sesion.")


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> TokenResponse:
    email = body.email.strip().lower()
    ip = _client_ip(request)
    pair_key, ip_key = f"login:{ip}:{email}", f"login-ip:{ip}"
    wait = max(
        rate_limit.retry_after(pair_key, LOGIN_MAX_PER_EMAIL_IP, LOGIN_WINDOW),
        rate_limit.retry_after(ip_key, LOGIN_MAX_PER_IP, LOGIN_WINDOW),
    )
    if wait:
        raise _too_many(wait)
    try:
        token = await login_with_password(db, email, body.password)
    except InvalidCredentials:
        rate_limit.record(pair_key, LOGIN_WINDOW)
        rate_limit.record(ip_key, LOGIN_WINDOW)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Correo o contrasena incorrectos"
        )
    rate_limit.reset(pair_key)
    return TokenResponse(access_token=token)


def _page(title: str, message: str, status_code: int = 200) -> HTMLResponse:
    html = (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title></head>"
        '<body style="font-family:system-ui,sans-serif;max-width:420px;margin:15vh auto;'
        'padding:0 24px;text-align:center">'
        f"<h1>{title}</h1><p>{message}</p></body></html>"
    )
    return HTMLResponse(html, status_code=status_code)
