import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str


class GoogleStatusResponse(BaseModel):
    connected: bool


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt solo procesa 72 bytes; mas largo se truncaria sin aviso.
        if len(value.encode("utf-8")) > 72:
            raise ValueError("La contrasena no puede pasar de 72 bytes")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
