import uuid

from pydantic import BaseModel


class VoiceTokenRequest(BaseModel):
    campaign_id: uuid.UUID
    # Rep-lookup path: caller selected a specific representative.
    target_phone_override: str | None = None
    target_rep_name: str | None = None
    target_rep_title: str | None = None


class VoiceTokenResponse(BaseModel):
    # Twilio Access Token JWT; "dev-token" when API key not configured.
    token: str
    # UUID passed to device.connect({ params: { session_id } }) so voice-app
    # can look up the Redis call state.
    session_id: str
