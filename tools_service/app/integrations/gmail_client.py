"""Cliente de bajo nivel para Gmail API.

Usado por app/tools/gmail_tool.py para leer correos recientes y extraer
pendientes accionables (PDF: reducir la carga de leer/priorizar correo,
fuente comun de sobrecarga cognitiva en TDAH).

La extraccion de "action items" en si (NLP) vive en agent_service via LLM;
este cliente solo trae el contenido crudo del correo.
"""

import base64

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def _service(credentials: Credentials):
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _extract_body(payload: dict) -> str:
    """Decodifica el primer body de texto plano encontrado en el payload
    (Gmail anida el contenido en `parts` para mensajes multipart)."""
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")
    for part in payload.get("parts", []):
        body = _extract_body(part)
        if body:
            return body
    return ""


def read_recent_emails(credentials: Credentials, max_results: int = 10) -> list[dict]:
    """Devuelve los `max_results` correos mas recientes de la bandeja de
    entrada con asunto, remitente y cuerpo en texto plano."""
    service = _service(credentials)
    message_list = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
        .execute()
        .get("messages", [])
    )

    emails = []
    for item in message_list:
        message = (
            service.users()
            .messages()
            .get(userId="me", id=item["id"], format="full")
            .execute()
        )
        headers = {h["name"]: h["value"] for h in message["payload"].get("headers", [])}
        emails.append(
            {
                "id": message["id"],
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "snippet": message.get("snippet", ""),
                "body": _extract_body(message["payload"]),
            }
        )
    return emails
