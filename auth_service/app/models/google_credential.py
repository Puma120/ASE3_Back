import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GoogleCredential(Base):
    """Tokens OAuth de Google por usuario (Calendar, Tasks, Gmail - scopes de
    usuario). Google Maps usa API key de aplicacion (tools_service/.env,
    GOOGLE_MAPS_API_KEY), no credencial por usuario, por eso no vive aqui.

    Pendiente: endpoint de consentimiento OAuth (/auth/google/callback) -
    diferido hasta tener un client_id/secret real de Google Cloud (ver
    cambios_para_el_documento.md). El modelo ya queda listo para recibirlo.
    """

    __tablename__ = "google_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    access_token: Mapped[str] = mapped_column(String(2048), nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    scopes: Mapped[str] = mapped_column(String(1024), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
