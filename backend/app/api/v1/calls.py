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
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import func, or_, select, update

from app.api.deps import DB
from app.api.v1.helpers import get_live_campaign_or_404, resolve_rep_or_422, resolve_target_ids
from app.config import settings
from app.dependencies import get_client_ip
from app.models.blocklist import BlocklistEntry
from app.models.call_session import CallSession
from app.redis_client import get_redis
from app.schemas.calls import CallCreateRequest, CallCreateResponse
from app.services.call_state import get_campaign_caller_id, save_call_state
from app.services.rate_limiter import check_rate_limit
from app.services.telephony import get_provider

log = structlog.get_logger()

router = APIRouter(tags=["calls"])


@router.post("/calls/create", response_model=CallCreateResponse)
async def create_call(body: CallCreateRequest, request: Request, db: DB) -> CallCreateResponse:
    """Initiate a phone callback for a supporter.

    Creates a CallSession, stores call state in Redis, then places an outbound
    Twilio call to the supporter's phone. Twilio calls voice-app which plays
    the intro and walks the supporter through each target.

    No auth required — this is a public endpoint called from org websites, so
    the blocklist, per-phone and per-IP rate limits and the campaign's call
    ceiling are all applied before any Twilio spend is incurred.
    """
    # 1. Validate campaign
    campaign = await get_live_campaign_or_404(body.campaign_id, db)

    if not campaign.allow_phone_callback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This campaign does not support phone callbacks"
        )

    # 2. Hash the canonical number for privacy-safe storage and rate limiting
    phone = body.phone_number
    phone_hash = hashlib.sha256(phone.encode()).hexdigest()
    ip = get_client_ip(request)

    # 3. Blocklist check — silent 403 to avoid confirming the number exists
    bl_result = await db.execute(
        select(BlocklistEntry)
        .where(or_(BlocklistEntry.phone_hash == phone_hash, BlocklistEntry.ip_address == ip))
        .limit(1)
    )
    if bl_result.scalar_one_or_none():
        log.warning("calls_create_blocklist_hit", phone_hash=phone_hash[:12], ip=ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This number is not eligible to participate")

    # 4. Rate limit by caller phone hash and by client IP
    redis = get_redis()
    await check_rate_limit(redis, "call", phone_hash, campaign.rate_limit)
    await check_rate_limit(redis, "call-ip", ip, campaign.rate_limit)

    # 5. Campaign-wide call ceiling
    if campaign.call_maximum is not None:
        count_result = await db.execute(
            select(func.count()).select_from(CallSession).where(CallSession.campaign_id == campaign.id)
        )
        if (count_result.scalar_one() or 0) >= campaign.call_maximum:
            log.warning("calls_create_campaign_maximum", campaign_id=str(campaign.id))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="This campaign has reached its call limit"
            )

    # 6. Twilio Lookup validation (only when credentials are present)
    if campaign.lookup_validate and settings.TWILIO_ACCOUNT_SID:
        loop = asyncio.get_running_loop()
        provider = get_provider()
        try:
            lookup = await loop.run_in_executor(None, provider.validate_phone, phone)
        except Exception:
            log.exception("lookup_failed", phone_hash=phone_hash[:12])
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Could not validate phone number")

        if not lookup.is_valid:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid phone number")

        if campaign.lookup_require_mobile and lookup.line_type != "mobile":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "Landline numbers cannot receive automated calls. "
                    "Please use the browser calling option instead."
                ),
            )

    # 7. Load targets (DB campaign targets or the rep behind the caller's handle)
    rep = await resolve_rep_or_422(body.rep_token, campaign.id)
    target_ids = await resolve_target_ids(campaign, db, rep=rep)

    if not target_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Campaign has no targets configured")

    if campaign.target_ordering == "shuffle" and rep is None:
        random.shuffle(target_ids)

    # 8. Persist CallSession
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

    # 9. Store call state in Redis (consumed by webhook chain)
    state = {
        "campaign_id": str(campaign.id),
        "target_ids": target_ids,
        "current_target_index": 0,
        "caller_phone_hash": phone_hash,
        "connection_type": "outbound_phone",
        "client_ip": ip,
    }
    await save_call_state(session_id, state)

    # 10. Place Twilio outbound call (skipped in dev when credentials are absent)
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
            # The CallSession row is already committed, so mark it failed rather
            # than leave it sitting at "initiated" forever. The Redis call state
            # expires on its own; the caller is free to retry.
            log.exception("twilio_create_call_failed", session_id=str(session_id))
            await db.execute(
                update(CallSession).where(CallSession.id == session_id).values(status="failed")
            )
            await db.commit()
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
