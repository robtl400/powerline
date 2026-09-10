"""Tests for the Twilio webhook call flow.

Covers the silent-caller retry in make-calls, the DTMF skip and empty-result
attributes in the generated TwiML, and the abandoned-session status mapping.
"""
from __future__ import annotations

import hashlib
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    keys = [f"rate:call-ip:{TEST_IP}"]
    keys += [
        f"rate:call:{hashlib.sha256(phone.encode()).hexdigest()}" for phone in MODULE_PHONES
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
