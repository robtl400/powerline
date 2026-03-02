import uuid

from pydantic import BaseModel


class CallCreateRequest(BaseModel):
    campaign_id: uuid.UUID
    phone_number: str  # E.164 format expected
    referral_code: str | None = None


class CallCreateResponse(BaseModel):
    session_id: str
    status: str  # "initiated"
