"""Public call creation endpoint — phone callback path.

No authentication required: this is called by the embedded widget or
org website on behalf of a supporter who wants to be called back.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
from app.config import settings
from app.models.blocklist import BlocklistEntry
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.redis_client import get_redis
from app.schemas.calls import CallCreateRequest, CallCreateResponse
from app.services.call_state import get_campaign_caller_id, save_call_state
from app.services.rate_limiter import check_rate_limit
from app.services.telephony import get_provider

log = structlog.get_logger()

router = APIRouter(tags=["calls"])


@router.post("/calls/create", response_model=CallCreateResponse)
async def create_call(body: CallCreateRequest, db: DB) -> CallCreateResponse:
    """Initiate a phone callback for a supporter.

    Creates a CallSession, stores call state in Redis, then places an outbound
    Twilio call to the supporter's phone. Twilio calls voice-app which plays
    the intro and walks the supporter through each target.

    No auth required — this is a public endpoint called from org websites.
    """
    # 1. Validate campaign
    result = await db.execute(select(Campaign).where(Campaign.id == body.campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign or campaign.status != "live":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active")

    if not campaign.allow_phone_callback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This campaign does not support phone callbacks"
        )

    # 2. Load targets in configured order
    ct_result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    campaign_targets = ct_result.scalars().all()
    target_ids = [str(ct.target_id) for ct in campaign_targets]

    if not target_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Campaign has no targets configured")

    if campaign.target_ordering == "shuffle":
        random.shuffle(target_ids)

    phone = body.phone_number

    # 3. Twilio Lookup validation (only when credentials are present)
    if campaign.lookup_validate and settings.TWILIO_ACCOUNT_SID:
        loop = asyncio.get_running_loop()
        provider = get_provider()
        try:
            lookup = await loop.run_in_executor(None, provider.validate_phone, phone)
        except Exception:
            log.exception("lookup_failed", phone=phone[:6])
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not validate phone number")

        if not lookup.is_valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid phone number")

        if campaign.lookup_require_mobile and lookup.line_type == "landline":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Landline numbers cannot receive automated calls. "
                    "Please use the browser calling option instead."
                ),
            )

    # 4. Hash phone for privacy-safe storage and rate limiting
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()

    # 5. Blocklist check — silent 403 to avoid confirming the number exists
    bl_result = await db.execute(
        select(BlocklistEntry).where(BlocklistEntry.phone_hash == phone_hash).limit(1)
    )
    if bl_result.scalar_one_or_none():
        log.warning("calls_create_blocklist_hit", phone_hash=phone_hash[:12])
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This number is not eligible to participate")

    # 6. Rate limit — dev bypass mirrors validate_twilio_request (no token = no enforcement)
    redis = get_redis()
    is_dev = not settings.TWILIO_AUTH_TOKEN
    await check_rate_limit(redis, phone_hash, campaign.rate_limit, is_admin=is_dev)

    # 7. Persist CallSession
    session_id = uuid.uuid4()
    session = CallSession(
        id=session_id,
        campaign_id=campaign.id,
        connection_type="outbound_phone",
        caller_phone_hash=phone_hash,
        from_number=phone,
        referral_code=body.referral_code,
        status="initiated",
    )
    db.add(session)
    await db.commit()

    log.info(
        "call_session_created",
        session_id=str(session_id),
        campaign_id=str(campaign.id),
        target_count=len(target_ids),
    )

    # 8. Store call state in Redis (consumed by webhook chain)
    state = {
        "campaign_id": str(campaign.id),
        "target_ids": target_ids,
        "current_target_index": 0,
        "caller_phone_hash": phone_hash,
        "connection_type": "outbound_phone",
    }
    await save_call_state(session_id, state)

    # 9. Place Twilio outbound call (skipped in dev when credentials are absent)
    if settings.TWILIO_ACCOUNT_SID and settings.PUBLIC_BASE_URL:
        caller_id = await get_campaign_caller_id(campaign.id, db)
        voice_url = (
            f"{settings.PUBLIC_BASE_URL}/webhooks/twilio/voice-app"
            f"?session_id={session_id}"
        )
        status_callback = f"{settings.PUBLIC_BASE_URL}/webhooks/twilio/status-callback"

        loop = asyncio.get_running_loop()
        provider = get_provider()
        try:
            await loop.run_in_executor(
                None,
                lambda: provider.create_call(
                    to=phone,
                    from_=caller_id,
                    url=voice_url,
                    status_callback=status_callback,
                    status_callback_event=["initiated", "ringing", "answered", "completed"],
                ),
            )
        except Exception:
            # Roll back the session so the caller can retry — state already in Redis
            # will expire naturally. Session row left as "initiated" for audit trail.
            log.exception("twilio_create_call_failed", session_id=str(session_id))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to place call — please try again"
            )
    else:
        log.info(
            "twilio_call_skipped_dev_mode",
            session_id=str(session_id),
            reason="TWILIO_ACCOUNT_SID or PUBLIC_BASE_URL not set",
        )

    return CallCreateResponse(session_id=str(session_id), status="initiated")
