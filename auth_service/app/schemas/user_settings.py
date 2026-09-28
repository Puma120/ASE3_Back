from pydantic import BaseModel


class UserSettingsResponse(BaseModel):
    timezone: str
    work_start_hour: int
    work_end_hour: int
    proactive_suggestions_enabled: bool
    focus_mode_enabled: bool

    model_config = {"from_attributes": True}


class UserSettingsUpdate(BaseModel):
    """Todos los campos opcionales: PATCH parcial de /users/me/settings."""

    timezone: str | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None
    proactive_suggestions_enabled: bool | None = None
    focus_mode_enabled: bool | None = None
