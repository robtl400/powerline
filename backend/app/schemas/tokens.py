import uuid

from pydantic import BaseModel, Field

from app.schemas.calls import TargetPreview


class VoiceTokenRequest(BaseModel):
    campaign_id: uuid.UUID
    # Handle issued by GET /campaigns/{id}/reps; resolved server-side to the
    # representative's phone number.
    rep_token: str | None = Field(default=None, max_length=64)


class VoiceTokenResponse(BaseModel):
    # Twilio Access Token JWT; "dev-token" when API key not configured.
    token: str
    # UUID passed to device.connect({ params: { session_id } }) so voice-app
    # can look up the Redis call state.
    session_id: str
    # First target in the settled dial order, which a shuffled campaign only
    # knows server-side. None when the target row could not be read back.
    first_target: TargetPreview | None = None
