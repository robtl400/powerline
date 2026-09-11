import ipaddress
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.schemas.common import Page

_PHONE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class BlocklistCreate(BaseModel):
    phone_number: str | None = None
    phone_hash: str | None = None
    ip_address: str | None = None
    reason: str | None = None

    @field_validator("phone_hash")
    @classmethod
    def validate_phone_hash(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _PHONE_HASH_RE.match(v):
            raise ValueError("phone_hash must be a lowercase hex SHA-256 digest")
        return v

    @field_validator("ip_address")
    @classmethod
    def validate_ip_address(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("ip_address must be a valid IPv4 or IPv6 address")
        return v

    @model_validator(mode="after")
    def require_at_least_one(self) -> "BlocklistCreate":
        if not self.phone_number and not self.phone_hash and not self.ip_address:
            raise ValueError(
                "At least one of phone_number, phone_hash or ip_address is required"
            )
        return self


class BlocklistResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    phone_hash: str | None
    ip_address: str | None
    reason: str | None
    created_by_id: uuid.UUID | None

    model_config = {"from_attributes": True}


BlocklistPage = Page[BlocklistResponse]
