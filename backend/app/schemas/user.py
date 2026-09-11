import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.target import normalize_phone
from app.services.auth import validate_password_strength

# Width of users.name — a longer value is a 422, not a DataError at commit.
NAME_MAX_LENGTH = 100


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(max_length=NAME_MAX_LENGTH)
    phone: str  # E.164 format
    password: str | None = None  # if omitted, a random password is generated and SMS'd
    role: Literal["admin", "staff"] = "staff"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    phone: str | None = None
    role: Literal["admin", "staff"] | None = None
    is_active: bool | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return normalize_phone(v)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    phone: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreateResponse(UserResponse):
    invite_sent: bool
