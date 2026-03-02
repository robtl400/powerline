import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas.target import TargetInCampaign

VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft": ["paused", "live"],
    "paused": ["live", "archived"],
    "live": ["paused", "archived"],
    "archived": [],
}


class CampaignCreate(BaseModel):
    name: str
    description: str | None = None
    campaign_type: str = "custom"
    language: str = "en-US"
    target_ordering: str = "in_order"
    call_maximum: int | None = None
    rate_limit: int | None = None
    allow_call_in: bool = False
    allow_webrtc: bool = True
    allow_phone_callback: bool = True
    lookup_validate: bool = True
    lookup_require_mobile: bool = False
    embed_config: dict = {}
    talking_points: str | None = None


class CampaignUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    campaign_type: str | None = None
    language: str | None = None
    target_ordering: str | None = None
    call_maximum: int | None = None
    rate_limit: int | None = None
    allow_call_in: bool | None = None
    allow_webrtc: bool | None = None
    allow_phone_callback: bool | None = None
    lookup_validate: bool | None = None
    lookup_require_mobile: bool | None = None
    embed_config: dict | None = None
    talking_points: str | None = None
    status: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("draft", "paused", "live", "archived"):
            raise ValueError(f"Invalid status: {v}")
        return v


class CampaignResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    name: str
    description: str | None
    status: str
    campaign_type: str
    language: str
    target_ordering: str
    call_maximum: int | None
    rate_limit: int | None
    allow_call_in: bool
    allow_webrtc: bool
    allow_phone_callback: bool
    lookup_validate: bool
    lookup_require_mobile: bool
    embed_config: dict
    talking_points: str | None
    created_by_id: uuid.UUID | None
    target_count: int = 0

    model_config = {"from_attributes": True}


class CampaignDetailResponse(CampaignResponse):
    targets: list[TargetInCampaign] = []


class TargetPublicInfo(BaseModel):
    """Target info safe to expose publicly — no phone number."""

    id: uuid.UUID
    name: str
    title: str
    location: str

    model_config = {"from_attributes": True}


class CampaignPublicResponse(BaseModel):
    """Public-facing campaign info returned to the embed widget.

    Omits internal fields (rate_limit, lookup_*, embed_config, created_by_id)
    and strips phone numbers from targets.
    """

    id: uuid.UUID
    name: str
    description: str | None
    talking_points: str | None
    allow_webrtc: bool
    allow_phone_callback: bool
    targets: list[TargetPublicInfo] = []

    model_config = {"from_attributes": True}


class CallCountResponse(BaseModel):
    total: int
    last_24h: int
    last_7d: int


class CampaignChecklist(BaseModel):
    targets_configured: bool
    audio_configured: bool
    phone_number_assigned: bool
    phone_verified: bool
    talking_points_written: bool
