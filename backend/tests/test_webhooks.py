"""Tests for the Twilio webhook call flow.

Covers the silent-caller retry in make-calls, the DTMF skip and empty-result
attributes in the generated TwiML, and the abandoned-session status mapping.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blocklist import BlocklistEntry
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.call_state import load_call_state, save_call_state
from app.services.telephony.twiml import (
    AudioConfig,
    build_gather_intro,
    build_target_intro_and_dial,
)

TEST_IP = "127.0.0.1"

MODULE_PHONES = [
    "+12025550401",
    "+12025550402",
    "+12025550403",
    "+12025550404",
]


@pytest.fixture(autouse=True)
async def clear_rate_buckets(redis):
    """Drop every rate-limit bucket this module touches, before and after."""
    keys = [f"rate:call-ip:{TEST_IP}", f"rate:call-webhook-ip:{TEST_IP}"]
    keys += [
        f"rate:{scope}:{hashlib.sha256(phone.encode()).hexdigest()}"
        for scope in ("call", "call-webhook")
        for phone in MODULE_PHONES
    ]
    await redis.delete(*keys)
    yield
    await redis.delete(*keys)


@pytest.fixture
async def flow(db: AsyncSession, campaign: Campaign):
    """A live campaign with one target, a CallSession, and Redis call state.

    The parent CallSid is unique per test so status-callback, which matches
    sessions by that SID, only ever touches this test's session.
    """
    campaign.status = "live"
    campaign.allow_phone_callback = True
    campaign.rate_limit = 20

    target = Target(
        name="Sen. Webhook",
        title="Senator",
        phone_number="+12025550500",
        location="WA",
    )
    db.add(target)
    await db.flush()
    db.add(CampaignTarget(campaign_id=campaign.id, target_id=target.id, order=0))

    call_sid = f"CAflow{uuid.uuid4().hex[:20]}"
    session = CallSession(
        id=uuid.uuid4(),
        campaign_id=campaign.id,
        connection_type="outbound_phone",
        caller_phone_hash=hashlib.sha256(MODULE_PHONES[0].encode()).hexdigest(),
        from_number=MODULE_PHONES[0],
        twilio_call_sid=call_sid,
        status="in_progress",
    )
    db.add(session)
    await db.commit()

    await save_call_state(
        session.id,
        {
            "campaign_id": str(campaign.id),
            "target_ids": [str(target.id)],
            "current_target_index": 0,
            "caller_phone_hash": session.caller_phone_hash,
            "connection_type": "outbound_phone",
            "client_ip": TEST_IP,
            "call_sid": call_sid,
        },
    )

    yield campaign, target, session, call_sid

    await db.execute(delete(Call).where(Call.session_id == session.id))
    await db.execute(delete(CallSession).where(CallSession.id == session.id))
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target.id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target.id))
    await db.commit()


# ---------------------------------------------------------------------------
# TwiML attributes
# ---------------------------------------------------------------------------


def test_gather_sets_action_on_empty_result() -> None:
    """A silent caller still reaches the action URL."""
    xml = build_gather_intro(
        AudioConfig(tts_text="Press any key"), {}, "/webhooks/twilio/make-calls"
    )
    assert 'actionOnEmptyResult="true"' in xml


def test_dial_sets_hangup_on_star() -> None:
    """The widget's * skip ends the dialed leg and hits the action URL."""
    xml = build_target_intro_and_dial(
        AudioConfig(tts_text="Connecting you now"),
        {},
        "+12025550500",
        "+12025550999",
        "/webhooks/twilio/call-complete",
    )
    assert 'hangupOnStar="true"' in xml


# ---------------------------------------------------------------------------
# make-calls: silent caller
# ---------------------------------------------------------------------------


async def test_make_calls_without_digits_reprompts_then_hangs_up(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """First silence re-asks the confirm prompt; the second ends the call."""
    _, _, session, call_sid = flow
    url = f"/webhooks/twilio/make-calls?session_id={session.id}"

    first = await client.post(url, data={"CallSid": call_sid})
    assert first.status_code == 200
    assert "<Gather" in first.text
    assert "<Redirect" not in first.text

    state = await load_call_state(str(session.id))
    assert state["gather_attempts"] == 1

    second = await client.post(url, data={"CallSid": call_sid})
    assert second.status_code == 200
    assert "<Hangup" in second.text
    assert "<Gather" not in second.text

    state = await load_call_state(str(session.id))
    assert state["gather_attempts"] == 2


async def test_make_calls_with_digits_proceeds_to_dial(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A keypress routes straight on to dial-target as before."""
    _, _, session, call_sid = flow

    resp = await client.post(
        f"/webhooks/twilio/make-calls?session_id={session.id}",
        data={"CallSid": call_sid, "Digits": "1"},
    )
    assert resp.status_code == 200
    assert "<Redirect" in resp.text
    assert "dial-target" in resp.text


async def test_dial_target_twiml_allows_star_skip(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """The dial served to a live call carries the skip attribute."""
    _, _, session, call_sid = flow

    resp = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert resp.status_code == 200
    assert 'hangupOnStar="true"' in resp.text


# ---------------------------------------------------------------------------
# status-callback: abandoned sessions
# ---------------------------------------------------------------------------


async def test_completed_without_calls_marks_session_failed(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A caller who hung up before any target was dialed did not complete."""
    _, _, session, call_sid = flow

    resp = await client.post(
        "/webhooks/twilio/status-callback",
        data={"CallSid": call_sid, "CallStatus": "completed", "CallDuration": "12"},
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(CallSession.status, CallSession.duration).where(CallSession.id == session.id)
    )
    assert result.one() == ("failed", 12)


async def test_completed_with_a_call_marks_session_completed(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """One logged Call row is enough to count the session as completed."""
    campaign, target, session, call_sid = flow

    db.add(Call(
        session_id=session.id,
        campaign_id=campaign.id,
        target_id=target.id,
        twilio_call_sid=f"CAleg-{uuid.uuid4().hex[:20]}",
        status="completed",
        duration=31,
    ))
    await db.commit()

    resp = await client.post(
        "/webhooks/twilio/status-callback",
        data={"CallSid": call_sid, "CallStatus": "completed", "CallDuration": "44"},
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(CallSession.status, CallSession.duration).where(CallSession.id == session.id)
    )
    assert result.one() == ("completed", 44)


async def test_in_progress_after_completed_leaves_the_session_completed(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A late or retried in-progress callback cannot reopen a finished session."""
    _, _, session, call_sid = flow
    await db.execute(
        update(CallSession).where(CallSession.id == session.id).values(status="completed")
    )
    await db.commit()

    resp = await client.post(
        "/webhooks/twilio/status-callback",
        data={"CallSid": call_sid, "CallStatus": "in-progress", "CallDuration": "9"},
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(CallSession.status, CallSession.duration).where(CallSession.id == session.id)
    )
    assert result.one() == ("completed", 9)


async def test_busy_status_still_maps_to_failed(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """The non-completed mappings are untouched by the abandoned-session rule."""
    _, _, session, call_sid = flow

    resp = await client.post(
        "/webhooks/twilio/status-callback",
        data={"CallSid": call_sid, "CallStatus": "busy"},
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(CallSession.status).where(CallSession.id == session.id)
    )
    assert result.scalar_one() == "failed"


# ---------------------------------------------------------------------------
# call-complete: unreached targets get the busy message
# ---------------------------------------------------------------------------


async def _two_target_state(session_id: uuid.UUID, target_id: uuid.UUID, call_sid: str) -> None:
    state = await load_call_state(str(session_id))
    state["target_ids"] = [str(target_id), str(target_id)]
    state["current_target_index"] = 0
    state["call_sid"] = call_sid
    await save_call_state(session_id, state)


@pytest.mark.parametrize("dial_status", ["busy", "no-answer", "failed", "canceled"])
async def test_call_complete_plays_busy_message_when_targets_remain(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
    dial_status: str,
) -> None:
    """An unreached target hands off with msg_target_busy, not msg_between_calls."""
    _, target, session, call_sid = flow
    await _two_target_state(session.id, target.id, call_sid)

    resp = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}",
        data={
            "CallSid": call_sid,
            "DialCallSid": f"CAleg{uuid.uuid4().hex[:16]}",
            "DialCallStatus": dial_status,
            "DialCallDuration": "0",
        },
    )
    assert resp.status_code == 200
    assert "That representative is unavailable" in resp.text
    assert "more calls" not in resp.text
    assert "dial-target" in resp.text


async def test_call_complete_plays_between_message_after_a_connected_target(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    _, target, session, call_sid = flow
    await _two_target_state(session.id, target.id, call_sid)

    resp = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}",
        data={
            "CallSid": call_sid,
            "DialCallSid": f"CAleg{uuid.uuid4().hex[:16]}",
            "DialCallStatus": "completed",
            "DialCallDuration": "42",
        },
    )
    assert resp.status_code == 200
    assert "more calls" in resp.text
    assert "That representative is unavailable" not in resp.text


# ---------------------------------------------------------------------------
# dial-target: the dialed leg, the end of the list, and a vanished target
# ---------------------------------------------------------------------------


async def test_dial_target_dials_the_current_target(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """The TwiML names the target's number and routes the result to call-complete."""
    _, target, session, call_sid = flow

    resp = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert resp.status_code == 200
    assert "<Dial" in resp.text
    assert target.phone_number in resp.text
    assert f"call-complete?session_id={session.id}" in resp.text
    assert 'hangupOnStar="true"' in resp.text


async def test_dial_target_past_the_last_target_says_goodbye(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    _, _, session, call_sid = flow
    state = await load_call_state(str(session.id))
    state["current_target_index"] = len(state["target_ids"])
    await save_call_state(session.id, state)

    resp = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Dial" not in resp.text


async def test_dial_target_says_goodbye_when_the_last_target_row_is_gone(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A target deleted mid-session ends the call rather than raising."""
    _, _, session, call_sid = flow
    state = await load_call_state(str(session.id))
    state["target_ids"] = [str(uuid.uuid4())]
    state["current_target_index"] = 0
    await save_call_state(session.id, state)

    resp = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Dial" not in resp.text


async def test_dial_target_skips_a_deleted_target_and_moves_to_the_next(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A target deleted mid-session costs that one call, not the whole session."""
    _, target, session, call_sid = flow
    state = await load_call_state(str(session.id))
    state["target_ids"] = [str(uuid.uuid4()), str(target.id)]
    state["current_target_index"] = 0
    await save_call_state(session.id, state)

    skipped = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert skipped.status_code == 200
    assert "<Redirect" in skipped.text
    assert "dial-target" in skipped.text
    assert "<Hangup" not in skipped.text

    state = await load_call_state(str(session.id))
    assert state["current_target_index"] == 1

    dialed = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert "<Dial" in dialed.text
    assert target.phone_number in dialed.text


# ---------------------------------------------------------------------------
# call-complete: one Call row per dialed leg
# ---------------------------------------------------------------------------


async def test_call_complete_answers_a_preexisting_call_row_as_a_duplicate(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A leg already in the calls table is answered again, never logged twice."""
    campaign, target, session, call_sid = flow
    await _two_target_state(session.id, target.id, call_sid)

    dial_sid = f"CAleg{uuid.uuid4().hex[:16]}"
    db.add(Call(
        session_id=session.id,
        campaign_id=campaign.id,
        target_id=target.id,
        twilio_call_sid=dial_sid,
        status="completed",
        duration=31,
    ))
    await db.commit()

    payload = {
        "CallSid": call_sid,
        "DialCallSid": dial_sid,
        "DialCallStatus": "completed",
        "DialCallDuration": "31",
    }
    first = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}", data=payload
    )
    second = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}", data=payload
    )
    assert first.status_code == 200
    assert first.text == second.text

    result = await db.execute(select(Call).where(Call.session_id == session.id))
    assert len(result.scalars().all()) == 1

    state = await load_call_state(str(session.id))
    assert state["current_target_index"] == 0


async def test_call_complete_without_a_dial_call_sid_logs_one_call_per_leg(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """With no leg SID to key on, the dialed index decides what is a retry."""
    _, target, session, call_sid = flow
    await _two_target_state(session.id, target.id, call_sid)

    dial = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session.id}",
        data={"CallSid": call_sid},
    )
    assert "<Dial" in dial.text

    payload = {
        "CallSid": call_sid,
        "DialCallStatus": "completed",
        "DialCallDuration": "20",
    }
    first = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}", data=payload
    )
    second = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session.id}", data=payload
    )
    assert first.status_code == 200
    assert first.text == second.text

    result = await db.execute(select(Call).where(Call.session_id == session.id))
    assert len(result.scalars().all()) == 1

    state = await load_call_state(str(session.id))
    assert state["current_target_index"] == 1


# ---------------------------------------------------------------------------
# Session ids that no handler can use
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("handler", ["voice-app", "make-calls", "dial-target", "call-complete"])
async def test_unknown_session_id_hangs_up(client: AsyncClient, handler: str) -> None:
    """A well-formed id with no Redis state gets a hangup, never a call."""
    resp = await client.post(
        f"/webhooks/twilio/{handler}?session_id={uuid.uuid4()}",
        data={"CallSid": f"CAghost{uuid.uuid4().hex[:16]}"},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Dial" not in resp.text


@pytest.mark.parametrize("handler", ["voice-app", "make-calls", "dial-target", "call-complete"])
@pytest.mark.parametrize("session_id", ["not-a-uuid", "", "../../etc/passwd", "1"])
async def test_malformed_session_id_hangs_up_instead_of_erroring(
    client: AsyncClient, handler: str, session_id: str
) -> None:
    resp = await client.post(
        f"/webhooks/twilio/{handler}?session_id={session_id}",
        data={"CallSid": f"CAjunk{uuid.uuid4().hex[:16]}"},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text


async def test_voice_app_hangs_up_when_the_session_belongs_to_another_call(
    client: AsyncClient,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A leaked session_id cannot be replayed from a different Twilio call."""
    _, _, session, call_sid = flow

    resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session.id}",
        data={"CallSid": f"CAother{uuid.uuid4().hex[:16]}"},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Gather" not in resp.text


# ---------------------------------------------------------------------------
# voice-app: the blocklist
# ---------------------------------------------------------------------------


async def test_voice_app_hangs_up_on_a_blocklisted_phone_hash(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """A number blocked after the session opened still never reaches a target."""
    _, _, session, call_sid = flow
    entry = BlocklistEntry(phone_hash=session.caller_phone_hash, reason="webhook test")
    db.add(entry)
    await db.commit()
    entry_id = entry.id

    try:
        resp = await client.post(
            f"/webhooks/twilio/voice-app?session_id={session.id}",
            data={"CallSid": call_sid, "From": "+12025550999", "To": MODULE_PHONES[0]},
        )
        assert resp.status_code == 200
        assert "<Hangup" in resp.text
        assert "<Gather" not in resp.text
    finally:
        await db.execute(delete(BlocklistEntry).where(BlocklistEntry.id == entry_id))
        await db.commit()


async def test_voice_app_hangs_up_on_a_blocklisted_caller_without_a_stored_hash(
    client: AsyncClient,
    db: AsyncSession,
    flow: tuple[Campaign, Target, CallSession, str],
) -> None:
    """With no hash in the state, the From number is hashed to match the blocklist."""
    _, _, session, call_sid = flow
    caller = MODULE_PHONES[1]

    state = await load_call_state(str(session.id))
    state["connection_type"] = "inbound_phone"
    state["caller_phone_hash"] = ""
    await save_call_state(session.id, state)

    entry = BlocklistEntry(
        phone_hash=hashlib.sha256(caller.encode()).hexdigest(), reason="webhook test"
    )
    db.add(entry)
    await db.commit()
    entry_id = entry.id

    try:
        resp = await client.post(
            f"/webhooks/twilio/voice-app?session_id={session.id}",
            data={"CallSid": call_sid, "From": caller},
        )
        assert resp.status_code == 200
        assert "<Hangup" in resp.text
        assert "<Gather" not in resp.text
    finally:
        await db.execute(delete(BlocklistEntry).where(BlocklistEntry.id == entry_id))
        await db.commit()
