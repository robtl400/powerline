import uuid
from datetime import datetime

import phonenumbers
from phonenumbers import PhoneNumberFormat
from pydantic import BaseModel, field_validator


def _normalize_phone(v: str) -> str:
    try:
        parsed = phonenumbers.parse(v, None)
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone number — include country code (e.g. +12025551234)")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Phone number is not valid")
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


class TargetCreate(BaseModel):
    name: str
    title: str
    phone_number: str
    location: str
    external_id: str | None = None
    target_metadata: dict = {}

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _normalize_phone(v)


class TargetUpdate(BaseModel):
    name: str | None = None
    title: str | None = None
    phone_number: str | None = None
    location: str | None = None
    external_id: str | None = None
    target_metadata: dict | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _normalize_phone(v)


class TargetResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    name: str
    title: str
    phone_number: str
    location: str
    external_id: str | None
    target_metadata: dict

    model_config = {"from_attributes": True}


class TargetInCampaign(TargetResponse):
    order: int


class ReorderRequest(BaseModel):
    target_ids: list[uuid.UUID]
