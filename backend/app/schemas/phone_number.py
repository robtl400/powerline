import uuid
from datetime import datetime

from pydantic import BaseModel


class PhoneNumberResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    number: str
    twilio_sid: str
    provider: str
    label: str
    capabilities: dict
    trust_status: str
    trust_product_sid: str | None

    model_config = {"from_attributes": True}


class CampaignAssignRequest(BaseModel):
    campaign_id: uuid.UUID
