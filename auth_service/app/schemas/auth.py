import uuid

from pydantic import BaseModel, EmailStr


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str

    model_config = {"from_attributes": True}


class GoogleStatusResponse(BaseModel):
    connected: bool
