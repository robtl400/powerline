import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class BlocklistCreate(BaseModel):
    phone_hash: str | None = None
    ip_address: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def require_at_least_one(self) -> "BlocklistCreate":
        if not self.phone_hash and not self.ip_address:
            raise ValueError("At least one of phone_hash or ip_address is required")
        return self


class BlocklistResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    phone_hash: str | None
    ip_address: str | None
    reason: str | None
    created_by_id: uuid.UUID | None

    model_config = {"from_attributes": True}
