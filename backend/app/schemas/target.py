import re
import uuid
from datetime import datetime

import phonenumbers
from phonenumbers import PhoneNumberFormat
from pydantic import BaseModel, Field, field_validator

_NON_DIGITS = re.compile(r"\D")

# Number classes that bill the caller — or the campaign — for the connection
# rather than carrying a conversation with a person at the other end.
_BILLED_NUMBER_TYPES = frozenset(
    {
        phonenumbers.PhoneNumberType.PREMIUM_RATE,
        phonenumbers.PhoneNumberType.SHARED_COST,
        phonenumbers.PhoneNumberType.UAN,
        phonenumbers.PhoneNumberType.VOICEMAIL,
    }
)

# Column widths of app.models.target.Target. Every write path — the single-target
# endpoints and the CSV import — bounds its input against these.
MAX_LENGTHS: dict[str, int] = {
    "name": 200,
    "title": 100,
    "phone_number": 20,
    "location": 200,
    "external_id": 100,
}


def normalize_phone(v: str) -> str:
    try:
        parsed = phonenumbers.parse(v, None)
    except phonenumbers.NumberParseException:
        raise ValueError("Invalid phone number — include country code (e.g. +12025551234)")
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Phone number is not valid")
    e164 = phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    if len(e164) > MAX_LENGTHS["phone_number"]:
        raise ValueError(f"Phone number exceeds {MAX_LENGTHS['phone_number']} characters")
    return e164


def to_us_e164(value: str) -> str:
    """Return the canonical E.164 form of a US phone number.

    Accepts the shapes people actually type — "(202) 555-0123", "202-555-0123",
    "12025550123", "+12025550123" — and rejects anything that is not a valid US
    number, so a single canonical string is what gets hashed, rate limited,
    blocklisted and dialed. Premium-rate and other billed number classes are
    refused as well, so no path that dials can be pointed at a 1-900 line.
    """
    candidate = value.strip()
    if not candidate.startswith("+"):
        digits = _NON_DIGITS.sub("", candidate)
        if len(digits) == 10:
            candidate = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            candidate = f"+{digits}"

    normalized = normalize_phone(candidate)
    parsed = phonenumbers.parse(normalized, None)

    if phonenumbers.region_code_for_number(parsed) != "US":
        raise ValueError("Only US phone numbers are supported")

    if phonenumbers.number_type(parsed) in _BILLED_NUMBER_TYPES:
        raise ValueError("Premium-rate numbers are not supported")

    return normalized


class TargetCreate(BaseModel):
    name: str = Field(max_length=MAX_LENGTHS["name"])
    title: str = Field(max_length=MAX_LENGTHS["title"])
    phone_number: str
    location: str = Field(max_length=MAX_LENGTHS["location"])
    external_id: str | None = Field(default=None, max_length=MAX_LENGTHS["external_id"])
    target_metadata: dict = {}

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return to_us_e164(v)


class TargetUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=MAX_LENGTHS["name"])
    title: str | None = Field(default=None, max_length=MAX_LENGTHS["title"])
    phone_number: str | None = None
    location: str | None = Field(default=None, max_length=MAX_LENGTHS["location"])
    external_id: str | None = Field(default=None, max_length=MAX_LENGTHS["external_id"])
    target_metadata: dict | None = None

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return to_us_e164(v)


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


class ImportRowError(BaseModel):
    row: int
    error: str


class ImportResult(BaseModel):
    imported: int
    updated: int
    errors: list[ImportRowError]
