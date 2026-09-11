"""Public call creation endpoint — phone callback path.

No authentication required: this is called by the embedded widget or
org website on behalf of a supporter who wants to be called back.
"""
from __future__ import annotations

import asyncio
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import or_, select, update

from app.api.deps import DB
from app.api.v1.helpers import get_live_campaign_or_404, phone_hash, start_call_session
from app.config import settings
from app.dependencies import get_client_ip
from app.models.blocklist import BlocklistEntry
from app.models.call_session import CallSession
from app.redis_client import get_redis
from app.schemas.calls import CallCreateRequest, CallCreateResponse
from app.services.call_state import get_campaign_caller_id, load_call_state, save_call_state
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
    the blocklist and the per-phone and per-IP rate limits are applied before
    any Twilio credential is used, and the campaign's call ceiling is claimed
    in the same transaction that opens the session, before the outbound call.
    """
    # 1. Validate campaign
    campaign = await get_live_campaign_or_404(body.campaign_id, db)

    if not campaign.allow_phone_callback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="This campaign does not support phone callbacks"
        )

    # 2. Hash the canonical number for privacy-safe storage and rate limiting
    phone = body.phone_number
    caller_hash = phone_hash(phone)
    ip = get_client_ip(request)

    # 3. Blocklist check — silent 403 to avoid confirming the number exists
    bl_result = await db.execute(
        select(BlocklistEntry)
        .where(or_(BlocklistEntry.phone_hash == caller_hash, BlocklistEntry.ip_address == ip))
        .limit(1)
    )
    if bl_result.scalar_one_or_none():
        log.warning("calls_create_blocklist_hit", phone_hash=caller_hash[:12], ip=ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This number is not eligible to participate")

    # 4. Rate limit by caller phone hash and by client IP
    redis = get_redis()
    await check_rate_limit(redis, "call", caller_hash, campaign.rate_limit)
    await check_rate_limit(redis, "call-ip", ip, campaign.rate_limit)

    # 5. Twilio Lookup validation (only when credentials are present)
    if campaign.lookup_validate and settings.TWILIO_ACCOUNT_SID:
        loop = asyncio.get_running_loop()
        provider = get_provider()
        try:
            lookup = await loop.run_in_executor(None, provider.validate_phone, phone)
        except Exception:
            log.exception("lookup_failed", phone_hash=caller_hash[:12])
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

    # 6. Claim a slot under the campaign ceiling, open the session, store its state
    started = await start_call_session(
        campaign,
        db,
        connection_type="outbound_phone",
        rep_token=body.rep_token,
        client_ip=ip,
        caller_phone_hash=caller_hash,
        referral_code=body.referral_code,
    )
    session_id = started.session_id

    # 7. Place Twilio outbound call (skipped in dev when credentials are absent)
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

    return CallCreateResponse(
        session_id=str(session_id),
        status="initiated",
        first_target=started.first_target,
    )


@router.post("/calls/{session_id}/skip", status_code=status.HTTP_204_NO_CONTENT)
async def skip_current_target(session_id: uuid.UUID, request: Request) -> None:
    """Ask the call flow to hang up on the target it is dialing and move on.

    No auth required — the supporter's own widget posts this while the call is
    up, and the session id is the only capability involved. The request is a
    signal, not a command: it records the index the caller is on, and the
    call-complete webhook logs that target as skipped and advances. A signal
    for an index the flow has already left is therefore harmless.

    Raises:
        HTTPException: 404 when the session has no live call state, which is
            the same answer an unknown session id gets.
    """
    ip = get_client_ip(request)
    await check_rate_limit(get_redis(), "skip", ip, settings.PUBLIC_RATE_LIMIT)

    state = await load_call_state(str(session_id))
    if not state:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call not found")

    state["skip_requested"] = int(state["current_target_index"])
    await save_call_state(session_id, state)

    log.info(
        "call_skip_requested",
        session_id=str(session_id),
        target_index=state["skip_requested"],
    )
