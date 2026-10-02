from zoneinfo import available_timezones

from pydantic import BaseModel, Field, field_validator


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
    work_start_hour: int | None = Field(default=None, ge=0, le=23)
    work_end_hour: int | None = Field(default=None, ge=1, le=24)
    proactive_suggestions_enabled: bool | None = None
    focus_mode_enabled: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str | None) -> str | None:
        if value is not None and value not in available_timezones():
            raise ValueError("Zona horaria IANA invalida")
        return value
