import uuid

from pydantic import BaseModel


class VoiceTokenRequest(BaseModel):
    campaign_id: uuid.UUID


class VoiceTokenResponse(BaseModel):
    # Twilio Access Token JWT; "dev-token" when API key not configured.
    token: str
    # UUID passed to device.connect({ params: { session_id } }) so voice-app
    # can look up the Redis call state.
    session_id: str
