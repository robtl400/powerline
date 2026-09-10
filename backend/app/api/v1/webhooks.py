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
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
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

_MAX_GATHER_ATTEMPTS = 2


def _hangup_xml() -> Response:
    """Return a plain hangup TwiML response for error paths."""
    from twilio.twiml.voice_response import VoiceResponse
    r = VoiceResponse()
    r.hangup()
    return Response(content=str(r), media_type="application/xml")


def _parse_session_id(session_id: str) -> uuid.UUID | None:
    """Return the session UUID, or None when the value is malformed."""
    try:
        return uuid.UUID(session_id)
    except (ValueError, AttributeError, TypeError):
        return None


async def _bound_state(handler: str, session_id: str, call_sid: str) -> dict | None:
    """Load call state and confirm it belongs to the incoming Twilio call.

    Returns None — the caller hangs up — when the state is gone or when the
    session is already bound to a different CallSid, so a leaked session_id
    cannot be replayed from another call.
    """
    state = await load_call_state(session_id)
    if not state:
        log.warning("webhook_state_missing", handler=handler, session_id=session_id, call_sid=call_sid)
        return None

    bound_sid = state.get("call_sid")
    if bound_sid and bound_sid != call_sid:
        log.warning(
            "webhook_call_sid_mismatch",
            handler=handler,
            session_id=session_id,
            call_sid=call_sid,
            bound_call_sid=bound_sid,
        )
        return None

    return state


async def _session_has_calls(call_sid: str, db: AsyncSession) -> bool:
    """True when the session bound to this parent CallSid logged any Call row."""
    result = await db.execute(
        select(Call.id)
        .join(CallSession, CallSession.id == Call.session_id)
        .where(CallSession.twilio_call_sid == call_sid)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


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
      1. Verify the call really belongs to this session (WebRTC identity and
         CallSid binding)
      2. Rate-limit by caller identifier (phone hash or From number)
      3. Check the blocklist — hang up immediately if blocked
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    call_sid = form.get("CallSid", "")

    if not session_id:
        log.warning("voice_app_no_session_id", call_sid=call_sid)
        return _hangup_xml()

    session_uuid = _parse_session_id(session_id)
    if session_uuid is None:
        log.warning("voice_app_bad_session_id", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    state = await load_call_state(session_id)
    if not state:
        log.warning("voice_app_state_missing", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    # WebRTC sessions may only be claimed by the Twilio client identity the
    # AccessToken was minted for.
    if state.get("connection_type") == "webrtc" and form.get("From") != f"client:{session_id}":
        log.warning(
            "voice_app_identity_mismatch",
            session_id=session_id,
            call_sid=call_sid,
            from_=form.get("From", ""),
        )
        return _hangup_xml()

    bound_sid = state.get("call_sid")
    if bound_sid and bound_sid != call_sid:
        log.warning(
            "voice_app_call_sid_mismatch",
            session_id=session_id,
            call_sid=call_sid,
            bound_call_sid=bound_sid,
        )
        return _hangup_xml()

    state["call_sid"] = call_sid
    await save_call_state(session_id, state)

    campaign_id = uuid.UUID(state["campaign_id"])

    # Load campaign to get rate_limit config.
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = camp_result.scalar_one_or_none()

    if campaign is None:
        log.warning("voice_app_campaign_not_found", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    # Identifier for rate-limiting and blocklist: prefer stored phone hash,
    # fall back to the From number Twilio provides.
    identifier = state.get("caller_phone_hash") or form.get("From", "")

    # Rate limit check — raises 429 if exceeded.
    redis = get_redis()
    await check_rate_limit(redis, "call", identifier, campaign.rate_limit)

    # Blocklist check — hang up silently if the caller or their IP is blocked.
    client_ip = state.get("client_ip") or ""
    conditions = []
    if identifier:
        conditions.append(BlocklistEntry.phone_hash == identifier)
    if client_ip:
        conditions.append(BlocklistEntry.ip_address == client_ip)

    if conditions:
        bl_result = await db.execute(
            select(BlocklistEntry).where(or_(*conditions)).limit(1)
        )
        if bl_result.scalar_one_or_none():
            log.warning(
                "blocklist_hit",
                identifier=identifier[:12],
                ip=client_ip,
                session_id=session_id,
                call_sid=call_sid,
            )
            return _hangup_xml()

    # Persist the Twilio CallSid and advance status to in_progress.
    await db.execute(
        update(CallSession)
        .where(CallSession.id == session_uuid)
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

    A <Gather> with actionOnEmptyResult also lands here when the caller stayed
    silent. The confirm prompt is re-asked once; a second silence ends the call
    rather than dialing targets nobody is listening to.
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    call_sid = form.get("CallSid", "")

    if not session_id or _parse_session_id(session_id) is None:
        log.warning("make_calls_bad_session_id", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    state = await _bound_state("make_calls", session_id, call_sid)
    if not state:
        return _hangup_xml()

    campaign_id = uuid.UUID(state["campaign_id"])

    if not form.get("Digits"):
        attempts = int(state.get("gather_attempts") or 0) + 1
        state["gather_attempts"] = attempts
        await save_call_state(session_id, state)
        log.info(
            "make_calls_no_digits",
            session_id=session_id,
            call_sid=call_sid,
            attempts=attempts,
        )

        if attempts < _MAX_GATHER_ATTEMPTS:
            confirm_audio = await get_audio_config("msg_intro_confirm", campaign_id, db)
            action_url = f"/webhooks/twilio/make-calls?session_id={session_id}"
            twiml = build_gather_intro(confirm_audio, {}, action_url)
            return Response(content=twiml, media_type="application/xml")

        goodbye_audio = await get_audio_config("msg_goodbye", campaign_id, db)
        return Response(
            content=build_goodbye(goodbye_audio, {}), media_type="application/xml"
        )

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
    call_sid = form.get("CallSid", "")

    if not session_id or _parse_session_id(session_id) is None:
        log.warning("dial_target_bad_session_id", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    state = await _bound_state("dial_target", session_id, call_sid)
    if not state:
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
        log.error(
            "dial_target_not_found",
            target_id=str(target_id),
            session_id=session_id,
            call_sid=call_sid,
        )
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

    Twilio retries this callback, so a repeat of a DialCallSid already logged
    for the session is answered with the same TwiML without writing a second
    Call row or skipping a target.
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    dial_status = form.get("DialCallStatus", "completed")
    dial_call_sid = form.get("DialCallSid", "")
    parent_call_sid = form.get("CallSid", "")

    try:
        dial_duration = int(form.get("DialCallDuration") or 0)
    except (TypeError, ValueError):
        log.warning(
            "call_complete_bad_duration",
            session_id=session_id,
            call_sid=parent_call_sid,
            raw=str(form.get("DialCallDuration"))[:20],
        )
        dial_duration = 0

    session_uuid = _parse_session_id(session_id)
    if not session_id or session_uuid is None:
        log.warning("call_complete_bad_session_id", session_id=session_id, call_sid=parent_call_sid)
        return _hangup_xml()

    state = await _bound_state("call_complete", session_id, parent_call_sid)
    if not state:
        return _hangup_xml()

    target_ids: list[str] = state["target_ids"]
    idx: int = state["current_target_index"]
    campaign_id = uuid.UUID(state["campaign_id"])

    # Map Twilio's hyphenated status to our underscore enum values. Anything
    # unrecognised is a failure, never a silent success.
    _status_map = {
        "completed": "completed",
        "answered": "completed",
        "busy": "busy",
        "no-answer": "no_answer",
        "failed": "failed",
        "canceled": "canceled",
        "in-progress": "in_progress",
        "ringing": "ringing",
        "queued": "queued",
    }
    call_status = _status_map.get(dial_status, "failed")

    duplicate = False
    if dial_call_sid:
        existing = await db.execute(
            select(Call.id)
            .where(Call.session_id == session_uuid, Call.twilio_call_sid == dial_call_sid)
            .limit(1)
        )
        duplicate = existing.scalar_one_or_none() is not None

    if duplicate:
        log.info(
            "call_complete_duplicate",
            session_id=session_id,
            call_sid=dial_call_sid,
        )
        next_idx = idx
    else:
        # Persist the Call record.
        if idx < len(target_ids):
            call = Call(
                session_id=session_uuid,
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
                call_sid=dial_call_sid or parent_call_sid,
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
            .where(CallSession.id == session_uuid)
            .values(status="completed")
        )
        await db.commit()
        log.info("session_completed", session_id=session_id, call_sid=parent_call_sid)
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

    if not call_sid:
        log.warning("status_callback_no_call_sid", raw_status=raw_status)
        return Response(content="", status_code=200)

    try:
        call_duration = int(form.get("CallDuration") or 0)
    except (TypeError, ValueError):
        log.warning("status_callback_bad_duration", call_sid=call_sid)
        call_duration = 0

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
        log.debug("status_callback_skipped", call_sid=call_sid, raw_status=raw_status)
        return Response(content="", status_code=200)

    # A parent call that hung up before any target was dialed is an abandoned
    # session, not a completed one — only Call rows prove work happened.
    if session_status == "completed" and not await _session_has_calls(call_sid, db):
        log.info("status_callback_abandoned_session", call_sid=call_sid)
        session_status = "failed"

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
