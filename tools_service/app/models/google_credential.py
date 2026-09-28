import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class GoogleCredential(Base):
    """Espejo de solo-lectura de auth_service.app.models.google_credential -
    misma tabla, misma base de datos Postgres compartida (ver Fig. 3.1:
    ToolsService <--> SQL). tools_service nunca escribe aqui; el flujo OAuth
    y la renovacion de tokens son responsabilidad de auth_service."""

    __tablename__ = "google_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(2048))
    refresh_token: Mapped[str | None] = mapped_column(String(2048))
    scopes: Mapped[str] = mapped_column(String(1024))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
