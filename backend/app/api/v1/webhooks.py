"""Twilio webhook endpoints for the call flow state machine.

All routes are POST (Twilio always POSTs to webhooks) and protected by
validate_twilio_request. In dev mode (empty TWILIO_AUTH_TOKEN) that
dependency is skipped automatically.

Call flow order:
  voice-app → make-calls → dial-target → call-complete
                  ↑___________|  (loops back while targets remain)

status-callback is called asynchronously by Twilio for parent call events.
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
from app.config import settings
from app.dependencies import validate_twilio_request
from app.models.blocklist import BlocklistEntry
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.target import Target
from app.redis_client import get_redis
from app.services.audio_service import get_audio_config
from app.services.call_state import get_campaign_caller_id, load_call_state, save_call_state
from app.services.rate_limiter import check_rate_limit
from app.services.telephony.twiml import (
    build_between_targets,
    build_gather_intro,
    build_goodbye,
    build_target_intro_and_dial,
)

log = structlog.get_logger()

router = APIRouter(tags=["webhooks"])


def _hangup_xml() -> Response:
    """Return a plain hangup TwiML response for error paths."""
    from twilio.twiml.voice_response import VoiceResponse
    r = VoiceResponse()
    r.hangup()
    return Response(content=str(r), media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: voice-app (entry point)
# ---------------------------------------------------------------------------

@router.post("/voice-app")
async def voice_app(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Entry point called by Twilio when a call connects to the TwiML App.

    session_id arrives either as a URL query param (phone callback path) or
    as a custom TwiML App parameter in the POST body (WebRTC path).

    Before playing the intro we:
      1. Rate-limit by caller identifier (phone hash or From number)
      2. Check the blocklist — hang up immediately if blocked
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    call_sid = form.get("CallSid", "")

    if not session_id:
        log.warning("voice_app_no_session_id", call_sid=call_sid)
        return _hangup_xml()

    state = await load_call_state(session_id)
    if not state:
        log.warning("voice_app_state_missing", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    campaign_id = uuid.UUID(state["campaign_id"])

    # Load campaign to get rate_limit config.
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = camp_result.scalar_one_or_none()

    # Identifier for rate-limiting and blocklist: prefer stored phone hash,
    # fall back to the From number Twilio provides.
    identifier = state.get("caller_phone_hash") or form.get("From", "")

    # Dev-mode bypass mirrors validate_twilio_request: no token = no enforcement.
    is_dev = not settings.TWILIO_AUTH_TOKEN

    # Rate limit check — raises 429 if exceeded.
    redis = get_redis()
    await check_rate_limit(
        redis=redis,
        identifier=identifier,
        limit=campaign.rate_limit if campaign else None,
        is_admin=is_dev,
    )

    # Blocklist check — hang up silently if the caller is blocked.
    if identifier:
        bl_result = await db.execute(
            select(BlocklistEntry)
            .where(BlocklistEntry.phone_hash == identifier)
            .limit(1)
        )
        if bl_result.scalar_one_or_none():
            log.warning("blocklist_hit", identifier=identifier[:12], session_id=session_id)
            return _hangup_xml()

    # Persist the Twilio CallSid and advance status to in_progress.
    await db.execute(
        update(CallSession)
        .where(CallSession.id == uuid.UUID(session_id))
        .values(twilio_call_sid=call_sid, status="in_progress")
    )
    await db.commit()

    intro_audio = await get_audio_config("msg_intro", campaign_id, db)
    confirm_audio = await get_audio_config("msg_intro_confirm", campaign_id, db)
    action_url = f"/webhooks/twilio/make-calls?session_id={session_id}"
    twiml = build_gather_intro(intro_audio, {}, action_url, confirm_audio=confirm_audio)
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: make-calls (after keypress Gather)
# ---------------------------------------------------------------------------

@router.post("/make-calls")
async def make_calls(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Called by Twilio after the caller presses a key in voice-app's <Gather>.

    Plays the block-intro message then redirects to dial-target.
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")

    if not session_id:
        return _hangup_xml()

    state = await load_call_state(session_id)
    if not state:
        log.warning("make_calls_state_missing", session_id=session_id)
        return _hangup_xml()

    campaign_id = uuid.UUID(state["campaign_id"])
    block_intro = await get_audio_config("msg_call_block_intro", campaign_id, db)
    redirect_url = f"/webhooks/twilio/dial-target?session_id={session_id}"
    twiml = build_between_targets(block_intro, {}, redirect_url)
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: dial-target
# ---------------------------------------------------------------------------

@router.post("/dial-target")
async def dial_target(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Announce the current target and dial them.

    Reads current_target_index from Redis to determine which target to call.
    The <Dial> action URL → call-complete logs the result and advances the index.
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")

    if not session_id:
        return _hangup_xml()

    state = await load_call_state(session_id)
    if not state:
        log.warning("dial_target_state_missing", session_id=session_id)
        return _hangup_xml()

    target_ids: list[str] = state["target_ids"]
    idx: int = state["current_target_index"]
    campaign_id = uuid.UUID(state["campaign_id"])

    if idx >= len(target_ids):
        # Overshot — all targets done; say goodbye.
        goodbye_audio = await get_audio_config("msg_goodbye", campaign_id, db)
        twiml = build_goodbye(goodbye_audio, {})
        return Response(content=twiml, media_type="application/xml")

    target_id = uuid.UUID(target_ids[idx])
    result = await db.execute(select(Target).where(Target.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        log.error("dial_target_not_found", target_id=str(target_id), session_id=session_id)
        return _hangup_xml()

    caller_id = await get_campaign_caller_id(campaign_id, db)

    context = {
        "name": target.name,
        "title": target.title or "",
        "location": target.location or "",
    }
    target_intro = await get_audio_config("msg_target_intro", campaign_id, db)
    action_url = f"/webhooks/twilio/call-complete?session_id={session_id}"
    twiml = build_target_intro_and_dial(
        target_intro, context, target.phone_number, caller_id, action_url
    )
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: call-complete (Dial action callback)
# ---------------------------------------------------------------------------

@router.post("/call-complete")
async def call_complete(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Called by Twilio when the dialed target leg ends.

    Logs a Call record, advances the target index in Redis, then either
    redirects to the next target or plays goodbye and hangs up.
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    dial_status = form.get("DialCallStatus", "completed")
    dial_duration = int(form.get("DialCallDuration", "0") or "0")
    dial_call_sid = form.get("DialCallSid", "")
    parent_call_sid = form.get("CallSid", "")

    if not session_id:
        return _hangup_xml()

    state = await load_call_state(session_id)
    if not state:
        log.warning("call_complete_state_missing", session_id=session_id)
        return _hangup_xml()

    target_ids: list[str] = state["target_ids"]
    idx: int = state["current_target_index"]
    campaign_id = uuid.UUID(state["campaign_id"])

    # Map Twilio's hyphenated status to our underscore enum values.
    _status_map = {
        "completed": "completed",
        "busy": "busy",
        "no-answer": "no_answer",
        "failed": "failed",
        "canceled": "canceled",
        "in-progress": "in_progress",
        "ringing": "ringing",
        "queued": "queued",
    }
    call_status = _status_map.get(dial_status, "completed")

    # Persist the Call record.
    if idx < len(target_ids):
        call = Call(
            session_id=uuid.UUID(session_id),
            campaign_id=campaign_id,
            target_id=uuid.UUID(target_ids[idx]),
            twilio_call_sid=dial_call_sid or parent_call_sid,
            status=call_status,
            duration=dial_duration,
        )
        db.add(call)
        await db.commit()
        log.info(
            "call_logged",
            session_id=session_id,
            target_id=target_ids[idx],
            status=call_status,
            duration=dial_duration,
        )

    # Advance to the next target.
    next_idx = idx + 1
    state["current_target_index"] = next_idx
    await save_call_state(session_id, state)

    if next_idx < len(target_ids):
        calls_left = len(target_ids) - next_idx
        between_audio = await get_audio_config("msg_between_calls", campaign_id, db)
        context = {"calls_left": str(calls_left)}
        redirect_url = f"/webhooks/twilio/dial-target?session_id={session_id}"
        twiml = build_between_targets(between_audio, context, redirect_url)
    else:
        # All targets done — mark session complete and hang up.
        await db.execute(
            update(CallSession)
            .where(CallSession.id == uuid.UUID(session_id))
            .values(status="completed")
        )
        await db.commit()
        goodbye_audio = await get_audio_config("msg_goodbye", campaign_id, db)
        twiml = build_goodbye(goodbye_audio, {})

    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: status-callback (async parent call status updates)
# ---------------------------------------------------------------------------

@router.post("/status-callback")
async def status_callback(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Asynchronous callback for the parent call's lifecycle events.

    Twilio sends this for every status transition (ringing, in-progress,
    completed, failed, etc.). We update the CallSession and duration here
    rather than in voice-app so the record is always up to date even if
    the caller drops before pressing a key.
    """
    form = dict(await request.form())
    call_sid = form.get("CallSid", "")
    raw_status = form.get("CallStatus", "")
    call_duration = int(form.get("CallDuration", "0") or "0")

    _status_map = {
        "in-progress": "in_progress",
        "completed": "completed",
        "failed": "failed",
        "busy": "failed",
        "no-answer": "failed",
        "canceled": "failed",
    }
    session_status = _status_map.get(raw_status)
    if not session_status:
        # Intermediate states (queued, ringing) — nothing to update yet.
        return Response(content="", status_code=200)

    updates: dict = {"status": session_status}
    if call_duration:
        updates["duration"] = call_duration

    await db.execute(
        update(CallSession)
        .where(CallSession.twilio_call_sid == call_sid)
        .values(**updates)
    )
    await db.commit()
    log.info("status_callback_processed", call_sid=call_sid, status=session_status)

    return Response(content="", status_code=200)
