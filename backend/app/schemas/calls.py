import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.target import to_us_e164


class CallCreateRequest(BaseModel):
    campaign_id: uuid.UUID
    phone_number: str  # normalized to E.164 by the validator below
    referral_code: str | None = Field(default=None, max_length=64)
    # Handle issued by GET /campaigns/{id}/reps; resolved server-side to the
    # representative's phone number.
    rep_token: str | None = Field(default=None, max_length=64)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return to_us_e164(v)


class CallCreateResponse(BaseModel):
    session_id: str
    status: str  # "initiated"
