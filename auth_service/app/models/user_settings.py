import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSettings(Base):
    """Configuraciones del sistema por usuario (Objetivo especifico 1 del
    PDF: "informacion estatica del perfil, configuraciones del sistema").

    - timezone / work_start_hour / work_end_hour: usados por
      tools_service.calendar_tool para no agendar sugerencias proactivas
      fuera del horario del usuario.
    - proactive_suggestions_enabled: apaga las sugerencias del agent_service
      (Objetivo especifico 4) sin desactivar el resto del chat.
    - focus_mode_enabled: preferencia de "Control de Enfoque" (DND) que
      tools_service.device_tool consulta antes de emitir el comando -
      recordar que solo tiene efecto real en front/mobile sobre Android.
    """

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    timezone: Mapped[str] = mapped_column(String(64), default="America/Mexico_City")
    work_start_hour: Mapped[int] = mapped_column(Integer, default=9)
    work_end_hour: Mapped[int] = mapped_column(Integer, default=18)
    proactive_suggestions_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    focus_mode_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
