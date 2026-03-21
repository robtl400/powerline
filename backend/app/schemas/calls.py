import uuid

from pydantic import BaseModel


class CallCreateRequest(BaseModel):
    campaign_id: uuid.UUID
    phone_number: str  # E.164 format expected
    referral_code: str | None = None
    # Rep-lookup path: caller selected a specific representative.
    # When set, call is routed to this phone instead of the campaign's DB targets.
    target_phone_override: str | None = None
    target_rep_name: str | None = None
    target_rep_title: str | None = None


class CallCreateResponse(BaseModel):
    session_id: str
    status: str  # "initiated"
