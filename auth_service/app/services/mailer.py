"""Envio de correo transaccional por la API HTTP de Resend (Railway bloquea el
SMTP saliente en varios planes, por eso no se usa smtplib)."""

import httpx

from app.core.config import settings


class MailNotConfigured(Exception):
    pass


class MailSendFailed(Exception):
    pass


async def send_mail(to: str, subject: str, html: str, text: str) -> None:
    if not settings.resend_api_key:
        raise MailNotConfigured
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                json={
                    "from": settings.mail_from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
    except httpx.HTTPError as exc:
        raise MailSendFailed from exc
    if response.status_code >= 300:
        raise MailSendFailed(f"resend {response.status_code}")


async def send_verification_email(to: str, full_name: str, link: str) -> None:
    subject = "Confirma tu correo en Oportuno"
    text = (
        f"Hola {full_name},\n\nConfirma tu correo para activar tu cuenta de Oportuno "
        f"(el enlace dura 24 horas):\n{link}\n\nSi no fuiste tu, ignora este mensaje."
    )
    html = (
        f"<p>Hola {_escape(full_name)},</p>"
        "<p>Confirma tu correo para activar tu cuenta de Oportuno "
        "(el enlace dura 24 horas).</p>"
        f'<p><a href="{_escape(link)}">Confirmar mi correo</a></p>'
        "<p>Si no fuiste tu, ignora este mensaje.</p>"
    )
    await send_mail(to, subject, html, text)


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
