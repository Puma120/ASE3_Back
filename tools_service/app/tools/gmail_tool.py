"""Tool: lectura de correos recientes (resumen/extraccion de acciones vive en
agent_service via LLM, esta tool solo trae y registra el contenido crudo).
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mongo import activity_logs
from app.integrations import gmail_client
from app.integrations.google_auth import get_user_credentials
from app.models.activity_log import build_activity_log


async def read_recent_emails(db: AsyncSession, user_id: uuid.UUID, max_results: int = 10) -> list[dict]:
    credentials = await get_user_credentials(db, user_id)
    emails = gmail_client.read_recent_emails(credentials, max_results)
    await activity_logs.insert_one(
        build_activity_log(
            str(user_id), "email_summarized", {"count": len(emails)}
        )
    )
    return emails
