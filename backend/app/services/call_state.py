"""Redis call-session state helpers.

All code that reads or writes the `call_session:{session_id}` Redis key should
go through this module so the key format and TTL are defined in one place.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.redis_client import get_redis

CALL_SESSION_TTL = 7200  # 2 hours


def _key(session_id: str | uuid.UUID) -> str:
    return f"call_session:{session_id}"


async def load_call_state(session_id: str) -> dict | None:
    """Return the call session state dict from Redis, or None if missing/expired."""
    raw = await get_redis().get(_key(session_id))
    return json.loads(raw) if raw else None


async def save_call_state(session_id: str | uuid.UUID, state: dict) -> None:
    """Write call state to Redis, refreshing the TTL."""
    await get_redis().set(_key(session_id), json.dumps(state), ex=CALL_SESSION_TTL)


async def get_campaign_caller_id(campaign_id: uuid.UUID, db: AsyncSession) -> str:
    """Return the first phone number assigned to the campaign, or the config fallback."""
    from app.models.campaign_phone_number import CampaignPhoneNumber
    from app.models.phone_number import PhoneNumber

    result = await db.execute(
        select(PhoneNumber.number)
        .join(CampaignPhoneNumber, PhoneNumber.id == CampaignPhoneNumber.phone_number_id)
        .where(CampaignPhoneNumber.campaign_id == campaign_id)
        .limit(1)
    )
    return result.scalar_one_or_none() or settings.TWILIO_FROM_NUMBER
