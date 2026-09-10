import re
import uuid

import phonenumbers
from pydantic import BaseModel, Field, field_validator

from app.schemas.target import normalize_phone

_NON_DIGITS = re.compile(r"\D")


def _to_us_e164(value: str) -> str:
    """Return the canonical E.164 form of a US phone number.

    Accepts the shapes supporters actually type — "(202) 555-0123",
    "202-555-0123", "12025550123", "+12025550123" — and rejects anything that
    is not a valid US number, so a single canonical string is what gets
    hashed, rate limited, blocklisted and dialed.
    """
    candidate = value.strip()
    if not candidate.startswith("+"):
        digits = _NON_DIGITS.sub("", candidate)
        if len(digits) == 10:
            candidate = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            candidate = f"+{digits}"

    normalized = normalize_phone(candidate)

    if phonenumbers.region_code_for_number(phonenumbers.parse(normalized, None)) != "US":
        raise ValueError("Only US phone numbers are supported")

    return normalized


class CallCreateRequest(BaseModel):
    campaign_id: uuid.UUID
    phone_number: str  # normalized to E.164 by the validator below
    referral_code: str | None = None
    # Handle issued by GET /campaigns/{id}/reps; resolved server-side to the
    # representative's phone number.
    rep_token: str | None = Field(default=None, max_length=64)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _to_us_e164(v)


class CallCreateResponse(BaseModel):
    session_id: str
    status: str  # "initiated"
