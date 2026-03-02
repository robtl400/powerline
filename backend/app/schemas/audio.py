import uuid
from datetime import datetime

from pydantic import BaseModel


class AudioRecordingCreate(BaseModel):
    key: str
    tts_text: str | None = None
    description: str | None = None


class AudioRecordingResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    campaign_id: uuid.UUID | None
    key: str
    version: int
    tts_text: str | None
    file_url: str | None
    description: str | None
    is_active: bool

    model_config = {"from_attributes": True}
