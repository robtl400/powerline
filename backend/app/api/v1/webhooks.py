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

import functools
import uuid
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from redis.exceptions import RedisError
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB
from app.api.v1.helpers import phone_hash
from app.dependencies import validate_twilio_request
from app.models.blocklist import BlocklistEntry
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.target import Target
from app.redis_client import get_redis
from app.services.audio_service import get_audio_config, get_audio_configs
from app.services.call_state import (
    CALL_SESSION_TTL,
    get_campaign_caller_id,
    load_call_state,
    save_call_state,
)
from app.services.rate_limiter import check_rate_limit
from app.services.telephony.twiml import (
    build_between_targets,
    build_gather_intro,
    build_goodbye,
    build_hangup,
    build_redirect,
    build_target_intro_and_dial,
)

log = structlog.get_logger()

router = APIRouter(tags=["webhooks"])

_MAX_GATHER_ATTEMPTS = 2

# Dial outcomes where the supporter never reached the target.
_UNREACHED_STATUSES = frozenset({"busy", "no_answer", "failed", "canceled"})

# Twilio's hyphenated dial statuses mapped to our underscore Call enum values.
# Anything unrecognised is a failure, never a silent success.
#
# "skipped" has no Twilio status of its own: a supporter who presses * ends the
# leg, which Twilio reports as completed. call-complete records that leg as
# skipped instead when the call state carries a skip marker for the same index,
# so a call the supporter cut short is not counted as one they saw through.
DIAL_STATUS_TO_CALL_STATUS = {
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

# CallSession statuses that no later callback may move away from.
_TERMINAL_SESSION_STATUSES = ("completed", "failed")

# Parent-call statuses mapped to CallSession statuses. Statuses absent here are
# intermediate and leave the session untouched.
CALL_STATUS_TO_SESSION_STATUS = {
    "in-progress": "in_progress",
    "completed": "completed",
    "failed": "failed",
    "busy": "failed",
    "no-answer": "failed",
    "canceled": "failed",
}


_Handler = TypeVar("_Handler", bound=Callable[..., Awaitable[Response]])


def _hangup_xml() -> Response:
    """Return a plain hangup TwiML response for error paths."""
    return Response(content=build_hangup(), media_type="application/xml")


def _twiml_on_error(handler: _Handler) -> _Handler:
    """Answer a failure raised inside a webhook with hangup TwiML.

    Twilio is an XML client: a JSON error body is an unparseable document that
    drops the call with no log of why. Every handler failure raised as an
    HTTPException — a rate limit, a 404 from a shared helper — is logged and
    answered with a hangup instead, and so is a Redis outage, which takes out
    the call state every handler reads.

    The signature check runs as a route dependency, before the handler, so its
    403 still reaches Twilio as a 403.
    """
    @functools.wraps(handler)
    async def wrapper(*args, **kwargs):
        try:
            return await handler(*args, **kwargs)
        except HTTPException as exc:
            log.warning(
                "webhook_http_error",
                handler=handler.__name__,
                status_code=exc.status_code,
            )
            return _hangup_xml()
        except RedisError as exc:
            log.error(
                "webhook_redis_error",
                handler=handler.__name__,
                error=type(exc).__name__,
            )
            return _hangup_xml()

    return wrapper  # type: ignore[return-value]


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


async def _webhook_form(request: Request) -> tuple[dict, str, str]:
    """Parse a webhook POST into its form, session id and parent CallSid.

    session_id arrives either as a URL query param (phone callback path) or as
    a custom TwiML App parameter in the POST body (WebRTC path).
    """
    form = dict(await request.form())
    session_id = request.query_params.get("session_id") or form.get("session_id", "")
    return form, session_id, form.get("CallSid", "")


async def _webhook_session(
    handler: str, request: Request
) -> tuple[dict, dict, str, str] | None:
    """Parse a webhook POST and load the call state the request belongs to.

    Returns (form, state, session_id, call_sid). Returns None — the caller
    answers with a hangup — when the session id is missing or malformed, when
    the state is gone, or when the session belongs to another Twilio call.
    """
    form, session_id, call_sid = await _webhook_form(request)

    if not session_id or _parse_session_id(session_id) is None:
        log.warning(
            f"{handler}_bad_session_id", session_id=session_id, call_sid=call_sid
        )
        return None

    state = await _bound_state(handler, session_id, call_sid)
    if not state:
        return None

    return form, state, session_id, call_sid


async def _claim_call_sid(
    redis, bind_key: str, call_sid: str
) -> tuple[bool, str | None]:
    """Claim the session for this CallSid, compare-and-set.

    SET NX is the compare-and-set that two calls racing on one leaked session
    id both go through, so exactly one of them wins the session. A claim that
    loses the race reads the holder: the same CallSid retrying its own webhook
    keeps the session, any other CallSid does not.

    A holder that has expired between the SET and the GET leaves nothing to
    compare against, so the claim is attempted once more; a second unreadable
    holder counts as another call's, never as this one's.

    Returns whether the session is this call's, and the CallSid holding it when
    it is not.
    """
    for _ in range(2):
        if await redis.set(bind_key, call_sid, nx=True, ex=CALL_SESSION_TTL):
            return True, None
        holder = await redis.get(bind_key)
        if holder:
            return holder == call_sid, holder
    return False, None


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
@_twiml_on_error
async def voice_app(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Entry point called by Twilio when a call connects to the TwiML App.

    session_id arrives either as a URL query param (phone callback path) or
    as a custom TwiML App parameter in the POST body (WebRTC path).

    Before playing the intro we:
      1. Verify the call really belongs to this session: a WebRTC call must
         come from the client identity the token was minted for, a phone
         callback must have been dialed to the number the session was opened
         for, and the session is claimed by the first CallSid to reach it
      2. Rate-limit the webhook itself, under its own scope so it never eats
         the budget /calls/create already spent: a phone session is counted
         per caller phone hash under "call-webhook", a WebRTC session per
         originating IP under "call-webhook-ip" — a WebRTC session id is
         single-use, so its IP is the only durable per-caller key
      3. Check the blocklist against the caller's phone hash and IP — hang up
         immediately if either is blocked

    A phone caller then hears the intro inside a <Gather> and starts the call
    block with a keypress. A WebRTC caller has no keypad to answer it with —
    the widget sends no digits but the * that skips a target — so the intro
    plays and the call goes straight on to the first target instead.
    """
    form, session_id, call_sid = await _webhook_form(request)

    if not session_id:
        log.warning("voice_app_no_session_id", call_sid=call_sid)
        return _hangup_xml()

    session_uuid = _parse_session_id(session_id)
    if session_uuid is None:
        log.warning("voice_app_bad_session_id", session_id=session_id, call_sid=call_sid)
        return _hangup_xml()

    state = await _bound_state("voice_app", session_id, call_sid)
    if not state:
        return _hangup_xml()

    connection_type = state.get("connection_type")
    caller_phone_hash = state.get("caller_phone_hash") or ""

    # WebRTC sessions may only be claimed by the Twilio client identity the
    # AccessToken was minted for.
    if connection_type == "webrtc" and form.get("From") != f"client:{session_id}":
        log.warning(
            "voice_app_identity_mismatch",
            session_id=session_id,
            call_sid=call_sid,
        )
        return _hangup_xml()

    # A phone callback is only this session's call when Twilio dialed the very
    # number the session was opened for.
    if connection_type == "outbound_phone" and caller_phone_hash:
        dialed = form.get("To", "")
        dialed_hash = phone_hash(dialed) if dialed else ""
        if dialed_hash != caller_phone_hash:
            log.warning(
                "voice_app_dialed_number_mismatch",
                session_id=session_id,
                call_sid=call_sid,
            )
            return _hangup_xml()

    redis = get_redis()

    bind_key = f"call_sid_bind:{session_id}"
    claimed, holder = await _claim_call_sid(redis, bind_key, call_sid)
    if not claimed:
        log.warning(
            "voice_app_call_sid_claimed",
            session_id=session_id,
            call_sid=call_sid,
            bound_call_sid=holder,
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

    # The blocklist stores digests, so the caller is identified by the session's
    # stored hash, falling back to a hash of the From number Twilio provides.
    # Only the digest is ever logged.
    from_number = form.get("From", "")
    identifier_hash = caller_phone_hash or (phone_hash(from_number) if from_number else "")
    client_ip = state.get("client_ip") or ""

    # Rate limit check — raises 429, which _twiml_on_error turns into a hangup.
    if connection_type == "webrtc":
        await check_rate_limit(redis, "call-webhook-ip", client_ip, campaign.rate_limit)
    else:
        await check_rate_limit(redis, "call-webhook", identifier_hash, campaign.rate_limit)

    # Blocklist check — hang up silently if the caller or their IP is blocked.
    conditions = []
    if identifier_hash:
        conditions.append(BlocklistEntry.phone_hash == identifier_hash)
    if client_ip:
        conditions.append(BlocklistEntry.ip_address == client_ip)

    if conditions:
        bl_result = await db.execute(
            select(BlocklistEntry).where(or_(*conditions)).limit(1)
        )
        if bl_result.scalar_one_or_none():
            log.warning(
                "blocklist_hit",
                phone_hash=identifier_hash[:12],
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

    if connection_type == "webrtc":
        intro_audio = await get_audio_config("msg_intro", campaign_id, db)
        dial_url = f"/webhooks/twilio/dial-target?session_id={session_id}"
        twiml = build_between_targets(intro_audio, {}, dial_url)
        return Response(content=twiml, media_type="application/xml")

    audio = await get_audio_configs(("msg_intro", "msg_intro_confirm"), campaign_id, db)
    action_url = f"/webhooks/twilio/make-calls?session_id={session_id}"
    twiml = build_gather_intro(
        audio["msg_intro"], {}, action_url, confirm_audio=audio["msg_intro_confirm"]
    )
    return Response(content=twiml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Endpoint: make-calls (after keypress Gather)
# ---------------------------------------------------------------------------

@router.post("/make-calls")
@_twiml_on_error
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

    Only phone callers reach this step: the WebRTC entry point goes straight to
    dial-target, having no keypress to wait for.
    """
    session = await _webhook_session("make_calls", request)
    if session is None:
        return _hangup_xml()
    form, state, session_id, call_sid = session

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
@_twiml_on_error
async def dial_target(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Announce the current target and dial them.

    Reads current_target_index from Redis to determine which target to call.
    The <Dial> action URL → call-complete logs the result and advances the index.

    A target whose row disappeared mid-session is skipped, not fatal: the index
    advances and the call is redirected here for the next target, or hears the
    goodbye once the list is exhausted.

    The index actually dialed is recorded in the state as dialed_index, which
    is how call-complete tells a first callback for a leg from a retry when
    Twilio sends no DialCallSid.
    """
    session = await _webhook_session("dial_target", request)
    if session is None:
        return _hangup_xml()
    _, state, session_id, call_sid = session

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
        next_idx = idx + 1
        state["current_target_index"] = next_idx
        await save_call_state(session_id, state)

        if next_idx < len(target_ids):
            redirect_url = f"/webhooks/twilio/dial-target?session_id={session_id}"
            return Response(
                content=build_redirect(redirect_url), media_type="application/xml"
            )

        goodbye_audio = await get_audio_config("msg_goodbye", campaign_id, db)
        return Response(
            content=build_goodbye(goodbye_audio, {}), media_type="application/xml"
        )

    caller_id = await get_campaign_caller_id(campaign_id, db)

    context = {
        "name": target.name,
        "title": target.title or "",
        "location": target.location or "",
    }
    if state.get("dialed_index") != idx:
        state["dialed_index"] = idx
        await save_call_state(session_id, state)

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
@_twiml_on_error
async def call_complete(
    request: Request,
    db: DB,
    _: None = Depends(validate_twilio_request),
) -> Response:
    """Called by Twilio when the dialed target leg ends.

    Logs a Call record, advances the target index in Redis, then either
    redirects to the next target or plays goodbye and hangs up.

    A leg the supporter chose to leave — the skip endpoint marks the index in
    the call state before the * hangs the leg up — is recorded as skipped
    rather than completed, and the marker is cleared here.

    A leg is keyed by its DialCallSid, or by f"{CallSid}:{index}" when Twilio
    created no child leg at all — an invalid, unreachable or geo-blocked
    number. Both forms are unique per leg, so the unique index on
    (session_id, twilio_call_sid) rejects a second row for a leg already
    logged without collapsing two distinct legs of one session into one row.

    Twilio retries this callback, so a repeat never writes a second Call row
    and never re-dials a target. A repeat is recognised three ways:
      * a leg SID already logged for the session, found by the pre-check or by
        the unique index that rejects the insert underneath it
      * an index already in the state's completed_legs
      * an index dial-target never dialed, which is how a retry looks once the
        first callback has moved the index on and Twilio sent no DialCallSid

    A repeat that reports the leg still in flight advances the index and adds
    the leg to completed_legs, so the state agrees with the row already in the
    table. The redirect back to dial-target is served only when the index has
    moved past the leg this callback reports; a chain that would not advance
    ends in the goodbye instead of re-dialing the same target.
    """
    session = await _webhook_session("call_complete", request)
    if session is None:
        return _hangup_xml()
    form, state, session_id, parent_call_sid = session

    session_uuid = uuid.UUID(session_id)
    dial_status = form.get("DialCallStatus", "completed")
    dial_call_sid = form.get("DialCallSid", "")

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

    target_ids: list[str] = state["target_ids"]
    idx: int = state["current_target_index"]
    campaign_id = uuid.UUID(state["campaign_id"])

    call_status = DIAL_STATUS_TO_CALL_STATUS.get(dial_status, "failed")

    completed_legs: list[int] = list(state.get("completed_legs") or [])
    dialed_index = state.get("dialed_index")

    # The leg this callback reports. dial-target records the index it dialed;
    # without it the current index is the most the state can say.
    leg_index = dialed_index if dialed_index is not None else idx

    # The parent CallSid is shared by every leg of the session, so a leg Twilio
    # gave no child SID for is keyed by its own index instead.
    leg_sid = dial_call_sid or f"{parent_call_sid}:{idx}"

    duplicate = False
    if dial_call_sid:
        existing = await db.execute(
            select(Call.id)
            .where(Call.session_id == session_uuid, Call.twilio_call_sid == dial_call_sid)
            .limit(1)
        )
        duplicate = existing.scalar_one_or_none() is not None
    elif idx in completed_legs or (dialed_index is not None and dialed_index != idx):
        duplicate = True

    # The skip endpoint marks the index the supporter asked to leave. Twilio
    # reports that leg as completed, so the marker is what tells the two apart.
    # The marker is read once, by the callback that logs the leg: a repeat
    # leaves it for the leg it was written for, and a marker on any other index
    # is stale and is dropped without effect.
    skip_requested = None
    if not duplicate:
        skip_requested = state.pop("skip_requested", None)
        if skip_requested == idx and call_status == "completed":
            call_status = "skipped"

    if not duplicate and idx < len(target_ids):
        call = Call(
            session_id=session_uuid,
            campaign_id=campaign_id,
            target_id=uuid.UUID(target_ids[idx]),
            twilio_call_sid=leg_sid,
            status=call_status,
            duration=dial_duration,
        )
        db.add(call)
        try:
            await db.commit()
        except IntegrityError:
            # The unique index on (session_id, twilio_call_sid) rejected a leg
            # that is already in the table.
            await db.rollback()
            duplicate = True
        else:
            log.info(
                "call_logged",
                session_id=session_id,
                call_sid=leg_sid,
                target_id=target_ids[idx],
                status=call_status,
                duration=dial_duration,
            )

    # A leg that is logged is finished, whichever check found the row: the
    # index moves on unless the state already accounted for that leg.
    advance = not duplicate or (dialed_index == idx and idx not in completed_legs)

    if duplicate:
        log.info(
            "call_complete_duplicate",
            session_id=session_id,
            call_sid=leg_sid,
            target_index=idx,
            advancing=advance,
        )

    if advance:
        next_idx = idx + 1
        state["current_target_index"] = next_idx
        if idx not in completed_legs:
            completed_legs.append(idx)
        state["completed_legs"] = completed_legs
        await save_call_state(session_id, state)
    else:
        next_idx = idx
        if skip_requested is not None:
            await save_call_state(session_id, state)

    if next_idx <= leg_index:
        # The index sits at or behind the leg that just ended, so a redirect
        # would dial that target again.
        log.error(
            "call_complete_no_progress",
            session_id=session_id,
            call_sid=leg_sid,
            target_index=idx,
            dialed_index=dialed_index,
            next_index=next_idx,
        )
        goodbye_audio = await get_audio_config("msg_goodbye", campaign_id, db)
        twiml = build_goodbye(goodbye_audio, {})
    elif next_idx < len(target_ids):
        calls_left = len(target_ids) - next_idx
        # A target that never picked up gets the "we'll move on" message instead
        # of the neutral between-calls one.
        slot = (
            "msg_target_busy"
            if call_status in _UNREACHED_STATUSES
            else "msg_between_calls"
        )
        between_audio = await get_audio_config(slot, campaign_id, db)
        context = {"calls_left": str(calls_left)}
        redirect_url = f"/webhooks/twilio/dial-target?session_id={session_id}"
        twiml = build_between_targets(between_audio, context, redirect_url)
    else:
        # All targets done — mark session complete and hang up. A session a
        # status callback already closed keeps the status it was given.
        await db.execute(
            update(CallSession)
            .where(
                CallSession.id == session_uuid,
                CallSession.status.not_in(_TERMINAL_SESSION_STATUSES),
            )
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
@_twiml_on_error
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

    completed and failed are terminal: a late or retried in-progress callback
    never walks a finished session back. The duration is written regardless,
    so the final figure Twilio reports still lands on a session that
    call-complete already closed.
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

    session_status = CALL_STATUS_TO_SESSION_STATUS.get(raw_status)
    if not session_status:
        # Intermediate states (queued, ringing) — nothing to update yet.
        log.debug("status_callback_skipped", call_sid=call_sid, raw_status=raw_status)
        return Response(content="", status_code=200)

    # A parent call that hung up before any target was dialed is an abandoned
    # session, not a completed one — only Call rows prove work happened.
    if session_status == "completed" and not await _session_has_calls(call_sid, db):
        log.info("status_callback_abandoned_session", call_sid=call_sid)
        session_status = "failed"

    if call_duration:
        await db.execute(
            update(CallSession)
            .where(CallSession.twilio_call_sid == call_sid)
            .values(duration=call_duration)
        )

    await db.execute(
        update(CallSession)
        .where(
            CallSession.twilio_call_sid == call_sid,
            CallSession.status.not_in(_TERMINAL_SESSION_STATUSES),
        )
        .values(status=session_status)
    )
    await db.commit()
    log.info("status_callback_processed", call_sid=call_sid, status=session_status)

    return Response(content="", status_code=200)
