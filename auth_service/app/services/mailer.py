"""Envio de correo transaccional por la API HTTP de EmailJS (Railway bloquea el
SMTP saliente en varios planes, por eso no se usa smtplib). El asunto y el
cuerpo viven en la plantilla de EmailJS; aqui solo se pasan las variables."""

import httpx

from app.core.config import settings


class MailNotConfigured(Exception):
    pass


class MailSendFailed(Exception):
    pass


def mail_configured() -> bool:
    return all(
        (
            settings.emailjs_service_id,
            settings.emailjs_template_id,
            settings.emailjs_public_key,
            settings.emailjs_private_key,
        )
    )


async def send_verification_email(to: str, full_name: str, link: str) -> None:
    if not mail_configured():
        raise MailNotConfigured
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.emailjs.com/api/v1.0/email/send",
                json={
                    "service_id": settings.emailjs_service_id,
                    "template_id": settings.emailjs_template_id,
                    "user_id": settings.emailjs_public_key,
                    "accessToken": settings.emailjs_private_key,
                    "template_params": {
                        "email": to,
                        "full_name": full_name,
                        "link": link,
                    },
                },
            )
    except httpx.HTTPError as exc:
        raise MailSendFailed from exc
    if response.status_code >= 300:
        raise MailSendFailed(f"emailjs {response.status_code}: {response.text[:200]}")
