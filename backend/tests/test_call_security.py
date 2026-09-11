"""Security tests for the public call-origination path.

Covers the rep-selection handle (no client-supplied dial targets), phone
canonicalisation, blocklist and rate-limit enforcement, campaign ceilings,
and the webhook bindings that tie a Twilio call to its session.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import phone_hash
from app.config import settings
from app.models.blocklist import BlocklistEntry
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.call_state import load_call_state, save_call_state
from app.services.civic_service import issue_rep_tokens, resolve_rep_token
from app.services.telephony.base import CallResult

TEST_IP = "127.0.0.1"

REP_PHONE = "+12025550777"

# Callers fired together at one campaign's call ceiling.
CEILING_PHONES = [
    "+12025550221",
    "+12025550222",
    "+12025550223",
    "+12025550224",
    "+12025550225",
    "+12025550226",
]

# Every caller number this module dials, so their per-phone buckets can be
# cleared between tests and between suite runs.
MODULE_PHONES = [
    "+12025550123",
    "+12025550201",
    "+12025550202",
    "+12025550203",
    "+12025550204",
    "+12025550205",
    "+12025550206",
    "+12025550207",
    "+12025550208",
    "+12025550209",
    "+12025550210",
    "+12025550211",
    "+12025550212",
    "+12025550213",
    "+12025550214",
    *CEILING_PHONES,
]


@pytest.fixture(autouse=True)
def mock_twilio():
    """Keep every test off the real Twilio API."""
    provider = MagicMock()
    provider.create_call.return_value = CallResult(sid="CAtest", status="queued")
    provider.validate_phone.return_value = MagicMock(is_valid=True, line_type="mobile")
    with patch("app.api.v1.calls.get_provider", return_value=provider):
        with patch("app.api.v1.tokens._build_access_token", return_value="dev-token"):
            yield provider


@pytest.fixture(autouse=True)
async def clear_rate_buckets(redis):
    """Drop every rate-limit bucket this module touches, before and after."""
    keys = [
        f"rate:call-ip:{TEST_IP}",
        f"rate:call-webhook-ip:{TEST_IP}",
        f"rate:token:{TEST_IP}",
        f"rate:reps:{TEST_IP}",
    ]
    keys += [
        f"rate:{scope}:{phone_hash(phone)}"
        for scope in ("call", "call-webhook")
        for phone in MODULE_PHONES
    ]
    await redis.delete(*keys)
    yield
    await redis.delete(*keys)


@pytest.fixture
async def live_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    """Live campaign accepting both connection types."""
    campaign.status = "live"
    campaign.allow_phone_callback = True
    campaign.allow_webrtc = True
    campaign.lookup_validate = False
    campaign.rate_limit = 5
    campaign.embed_config = {"target_levels": ["federal"]}
    await db.commit()
    await db.refresh(campaign)

    campaign_id = campaign.id
    yield campaign

    await db.execute(delete(Call).where(Call.campaign_id == campaign_id))
    await db.execute(delete(CallSession).where(CallSession.campaign_id == campaign_id))
    await db.commit()
    await db.execute(
        delete(Target).where(
            Target.external_id == "rep_lookup",
            ~exists().where(Call.target_id == Target.id),
        )
    )
    await db.commit()


@pytest.fixture
async def campaign_with_target(
    db: AsyncSession, live_campaign: Campaign
) -> tuple[Campaign, Target]:
    """Give the live campaign one configured DB target."""
    target = Target(
        name="Configured Senator",
        phone_number="+12025550300",
        title="Senator",
        location="WA",
    )
    db.add(target)
    await db.flush()

    db.add(CampaignTarget(campaign_id=live_campaign.id, target_id=target.id, order=0))
    await db.commit()

    target_id = target.id
    yield live_campaign, target

    await db.execute(delete(Call).where(Call.target_id == target_id))
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target_id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


async def _issue_token(campaign_id: uuid.UUID) -> str:
    reps = await issue_rep_tokens(
        str(campaign_id),
        [{"name": "Sen. Server", "title": "U.S. Senator", "phone": REP_PHONE, "level": "federal"}],
    )
    return reps[0]["rep_token"]


async def _dialed_phone(db: AsyncSession, session_id: str) -> str:
    state = await load_call_state(session_id)
    assert state is not None
    target_id = uuid.UUID(state["target_ids"][0])
    result = await db.execute(select(Target).where(Target.id == target_id))
    return result.scalar_one().phone_number


# ---------------------------------------------------------------------------
# Rep selection handle
# ---------------------------------------------------------------------------


async def test_rep_token_dials_server_stored_phone_on_calls_create(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
) -> None:
    """rep_token resolves server-side; a client-supplied dial target is ignored."""
    rep_token = await _issue_token(live_campaign.id)

    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(live_campaign.id),
            "phone_number": "+12025550201",
            "rep_token": rep_token,
            "target_phone_override": "+12025559999",
            "target_rep_name": "Attacker Rep",
        },
    )
    assert resp.status_code == 200, resp.text

    session_id = resp.json()["session_id"]
    assert await _dialed_phone(db, session_id) == REP_PHONE


async def test_rep_token_dials_server_stored_phone_on_tokens_voice(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
) -> None:
    """The WebRTC path resolves the same handle and ignores injected fields."""
    rep_token = await _issue_token(live_campaign.id)

    resp = await client.post(
        "/api/v1/tokens/voice",
        json={
            "campaign_id": str(live_campaign.id),
            "rep_token": rep_token,
            "target_phone_override": "+12025559999",
        },
    )
    assert resp.status_code == 200, resp.text

    session_id = resp.json()["session_id"]
    assert await _dialed_phone(db, session_id) == REP_PHONE


async def test_rep_token_calls_run_ahead_of_configured_targets(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A looked-up rep is added to the campaign's targets, not swapped in for them."""
    campaign, configured = campaign_with_target
    rep_token = await _issue_token(campaign.id)

    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(campaign.id),
            "phone_number": "+12025550204",
            "rep_token": rep_token,
        },
    )
    assert resp.status_code == 200, resp.text

    state = await load_call_state(resp.json()["session_id"])
    assert state is not None
    assert len(state["target_ids"]) == 2
    assert state["target_ids"][1] == str(configured.id)

    result = await db.execute(
        select(Target).where(Target.id == uuid.UUID(state["target_ids"][0]))
    )
    assert result.scalar_one().phone_number == REP_PHONE


async def test_unknown_rep_token_is_rejected(
    client: AsyncClient,
    live_campaign: Campaign,
) -> None:
    """An expired or invented handle is a 422, never a dial."""
    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(live_campaign.id),
            "phone_number": "+12025550202",
            "rep_token": "not-a-real-token",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == {
        "message": "Invalid or expired representative selection",
        "code": "rep_token_invalid",
    }

    token_resp = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(live_campaign.id), "rep_token": "not-a-real-token"},
    )
    assert token_resp.status_code == 422


async def test_rep_token_from_another_campaign_is_rejected(
    client: AsyncClient,
    live_campaign: Campaign,
) -> None:
    """A handle only resolves for the campaign it was issued for."""
    other_token = await _issue_token(uuid.uuid4())

    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(live_campaign.id),
            "phone_number": "+12025550203",
            "rep_token": other_token,
        },
    )
    assert resp.status_code == 422


async def test_display_format_rep_phone_is_dialed_in_e164(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
) -> None:
    """A rep's published number is canonicalised before it can be dialed."""
    lookup_result = [
        {
            "name": "Sen. Display",
            "title": "U.S. Senator",
            "phone": "(202) 555-0144 ext. 7",
            "level": "federal",
        },
    ]
    with patch("app.api.v1.reps.lookup_reps", new_callable=AsyncMock) as lookup:
        lookup.return_value = lookup_result
        reps_resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")

    assert reps_resp.status_code == 200, reps_resp.text
    rep_token = reps_resp.json()["reps"][0]["rep_token"]

    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(live_campaign.id),
            "phone_number": "+12025550209",
            "rep_token": rep_token,
        },
    )
    assert resp.status_code == 200, resp.text
    assert await _dialed_phone(db, resp.json()["session_id"]) == "+12025550144"


async def test_undialable_rep_phone_is_dropped_and_never_dialed(
    client: AsyncClient,
    live_campaign: Campaign,
    redis,
) -> None:
    """A rep with no usable US number gets no handle, and a planted one is refused."""
    candidates = [
        ("Sen. Dialable", "(202) 555-0310"),
        ("Sen. Foreign", "+442071838750"),
        ("Sen. Garbled", "call the main office"),
    ]
    issued = await issue_rep_tokens(
        str(live_campaign.id),
        [
            {"name": name, "title": "U.S. Senator", "phone": phone, "level": "federal"}
            for name, phone in candidates
        ],
    )
    assert [rep["name"] for rep in issued] == ["Sen. Dialable"]

    planted = secrets.token_urlsafe(24)
    await redis.set(
        f"rep_token:{planted}",
        json.dumps(
            {
                "campaign_id": str(live_campaign.id),
                "phone": "+442071838750",
                "name": "Sen. Foreign",
                "title": "U.S. Senator",
                "level": "federal",
            }
        ),
        ex=60,
    )

    try:
        resp = await client.post(
            "/api/v1/calls/create",
            json={
                "campaign_id": str(live_campaign.id),
                "phone_number": "+12025550210",
                "rep_token": planted,
            },
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"] == {
            "message": "Invalid or expired representative selection",
            "code": "rep_token_invalid",
        }
    finally:
        await redis.delete(f"rep_token:{planted}")


async def test_reps_response_carries_token_not_phone(
    client: AsyncClient,
    live_campaign: Campaign,
) -> None:
    """GET /reps hands out handles; the phone number never leaves the server."""
    sample = [
        {"name": "Sen. Smith", "title": "U.S. Senator", "phone": "+12025550100", "level": "federal"},
    ]
    with patch("app.api.v1.reps.lookup_reps", new_callable=AsyncMock) as lookup:
        lookup.return_value = sample
        resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")

    assert resp.status_code == 200, resp.text
    rep = resp.json()["reps"][0]
    assert rep["name"] == "Sen. Smith"
    assert rep["level"] == "federal"
    assert rep["rep_token"]
    assert "phone" not in rep


# ---------------------------------------------------------------------------
# Phone canonicalisation, blocklist, rate limits
# ---------------------------------------------------------------------------


async def test_phone_variants_share_one_hash_and_one_blocklist_entry(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Every spelling of a number normalizes to the same hash — and the same block."""
    campaign, _ = campaign_with_target
    variants = ["+12025550123", "12025550123", "(202) 555-0123"]
    expected_hash = phone_hash("+12025550123")

    session_ids = []
    for variant in variants:
        resp = await client.post(
            "/api/v1/calls/create",
            json={"campaign_id": str(campaign.id), "phone_number": variant},
        )
        assert resp.status_code == 200, f"{variant}: {resp.text}"
        session_ids.append(uuid.UUID(resp.json()["session_id"]))

    result = await db.execute(
        select(CallSession.caller_phone_hash).where(CallSession.id.in_(session_ids))
    )
    hashes = set(result.scalars().all())
    assert hashes == {expected_hash}

    entry = BlocklistEntry(phone_hash=expected_hash, reason="security test")
    db.add(entry)
    await db.commit()
    entry_id = entry.id

    try:
        for variant in variants:
            resp = await client.post(
                "/api/v1/calls/create",
                json={"campaign_id": str(campaign.id), "phone_number": variant},
            )
            assert resp.status_code == 403, f"{variant}: expected 403, got {resp.status_code}"
    finally:
        await db.execute(delete(BlocklistEntry).where(BlocklistEntry.id == entry_id))
        await db.commit()


async def test_non_us_number_is_rejected(
    client: AsyncClient,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A valid non-US number is refused before any Twilio spend."""
    campaign, _ = campaign_with_target

    resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": "+442071838750"},
    )
    assert resp.status_code == 422
    assert "US phone numbers" in resp.text


async def test_ip_blocklist_blocks_voice_token(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A blocklisted IP cannot obtain a WebRTC token."""
    campaign, _ = campaign_with_target

    entry = BlocklistEntry(ip_address=TEST_IP, reason="security test")
    db.add(entry)
    await db.commit()
    entry_id = entry.id

    try:
        resp = await client.post(
            "/api/v1/tokens/voice",
            json={"campaign_id": str(campaign.id)},
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "This number is not eligible to participate"
    finally:
        await db.execute(delete(BlocklistEntry).where(BlocklistEntry.id == entry_id))
        await db.commit()


async def test_forwarded_for_does_not_bypass_token_limit(
    client: AsyncClient,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """X-Forwarded-For is untrusted by default, so rotating it earns no extra tokens."""
    campaign, _ = campaign_with_target

    statuses = []
    for i in range(20):
        resp = await client.post(
            "/api/v1/tokens/voice",
            json={"campaign_id": str(campaign.id)},
            headers={"x-forwarded-for": f"203.0.113.{i + 1}"},
        )
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            break

    assert 429 in statuses, f"Expected a 429 within 20 spoofed requests, got {statuses}"


async def test_call_maximum_reached_returns_429(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Both public paths refuse once the campaign hit its lifetime call ceiling."""
    campaign, _ = campaign_with_target

    db.add(
        CallSession(
            campaign_id=campaign.id,
            connection_type="outbound_phone",
            status="initiated",
        )
    )
    campaign.call_maximum = 1
    await db.commit()

    resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": "+12025550204"},
    )
    assert resp.status_code == 429, resp.text
    assert resp.json()["detail"] == "This campaign has reached its call limit"

    token_resp = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(campaign.id)},
    )
    assert token_resp.status_code == 429, token_resp.text


async def test_call_maximum_holds_under_concurrent_requests(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Twice the ceiling, fired at once, still admits exactly the ceiling."""
    campaign, _ = campaign_with_target
    ceiling = len(CEILING_PHONES) // 2
    campaign.call_maximum = ceiling
    campaign.rate_limit = 100  # keep the per-IP bucket out of this test's way
    await db.commit()

    responses = await asyncio.gather(
        *(
            client.post(
                "/api/v1/calls/create",
                json={"campaign_id": str(campaign.id), "phone_number": phone},
            )
            for phone in CEILING_PHONES
        )
    )
    statuses = sorted(resp.status_code for resp in responses)
    assert statuses == [200] * ceiling + [429] * ceiling, statuses

    count_result = await db.execute(
        select(func.count()).select_from(CallSession).where(CallSession.campaign_id == campaign.id)
    )
    assert count_result.scalar_one() == ceiling


# ---------------------------------------------------------------------------
# Webhook session binding
# ---------------------------------------------------------------------------


async def test_voice_app_rejects_foreign_webrtc_identity(
    client: AsyncClient,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A WebRTC session may only be claimed by its own Twilio client identity."""
    campaign, _ = campaign_with_target

    token_resp = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(campaign.id)},
    )
    assert token_resp.status_code == 200, token_resp.text
    session_id = token_resp.json()["session_id"]

    resp = await client.post(
        "/webhooks/twilio/voice-app",
        data={
            "session_id": session_id,
            "CallSid": "CAforeign001",
            "From": "client:" + str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Gather" not in resp.text


async def test_voice_app_rejects_second_call_sid(
    client: AsyncClient,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Once bound to a CallSid, a session cannot be replayed from another call."""
    campaign, _ = campaign_with_target
    phone = "+12025550205"

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    first = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAbound001", "From": phone, "To": phone},
    )
    assert "<Gather" in first.text

    second = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAattacker001", "From": phone, "To": phone},
    )
    assert "<Hangup" in second.text
    assert "<Gather" not in second.text

    dial = await client.post(
        f"/webhooks/twilio/dial-target?session_id={session_id}",
        data={"CallSid": "CAattacker001"},
    )
    assert "<Hangup" in dial.text
    assert "<Dial" not in dial.text


async def test_status_callback_without_call_sid_changes_nothing(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """An empty CallSid must not match every session whose SID is still blank."""
    campaign, _ = campaign_with_target

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": "+12025550206"},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = uuid.UUID(create_resp.json()["session_id"])

    resp = await client.post(
        "/webhooks/twilio/status-callback",
        data={"CallSid": "", "CallStatus": "completed", "CallDuration": "42"},
    )
    assert resp.status_code == 200

    result = await db.execute(select(CallSession).where(CallSession.id == session_id))
    session = result.scalar_one()
    assert session.status == "initiated"
    assert session.duration is None


async def test_call_complete_is_idempotent_per_dial_call_sid(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A retried Dial callback logs one Call row and does not skip a target."""
    campaign, _ = campaign_with_target
    phone = "+12025550207"

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAdup001", "From": phone, "To": phone},
    )

    payload = {
        "CallSid": "CAdup001",
        "DialCallSid": "CAleg-dup001",
        "DialCallStatus": "completed",
        "DialCallDuration": "31",
    }
    first = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session_id}", data=payload
    )
    second = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session_id}", data=payload
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text

    result = await db.execute(
        select(Call).where(Call.session_id == uuid.UUID(session_id))
    )
    calls = result.scalars().all()
    assert len(calls) == 1, f"Expected one Call row, got {len(calls)}"

    state = await load_call_state(session_id)
    assert state["current_target_index"] == 1


async def test_unknown_dial_status_is_recorded_as_failed(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """An unrecognised DialCallStatus is a failure, not a silent success."""
    campaign, _ = campaign_with_target
    phone = "+12025550208"

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAunknown001", "From": phone, "To": phone},
    )

    cc_resp = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session_id}",
        data={
            "CallSid": "CAunknown001",
            "DialCallSid": "CAleg-unknown001",
            "DialCallStatus": "something-new",
            "DialCallDuration": "not-a-number",
        },
    )
    assert cc_resp.status_code == 200

    result = await db.execute(
        select(Call).where(Call.session_id == uuid.UUID(session_id))
    )
    call = result.scalar_one()
    assert call.status == "failed"
    assert call.duration == 0


# ---------------------------------------------------------------------------
# voice-app: the dialed number, and webhook rate limits of its own
# ---------------------------------------------------------------------------


async def test_voice_app_rejects_a_call_dialed_to_another_number(
    client: AsyncClient,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A phone session belongs to the number Twilio was told to dial, and no other."""
    campaign, _ = campaign_with_target
    phone = "+12025550211"

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAdialed001", "From": phone, "To": "+12025559998"},
    )
    assert resp.status_code == 200
    assert "<Hangup" in resp.text
    assert "<Gather" not in resp.text


async def test_voice_app_does_not_spend_the_budget_calls_create_already_spent(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """The webhook counts under its own scope, so one callback costs one call."""
    campaign, _ = campaign_with_target
    campaign.rate_limit = 1
    await db.commit()
    phone = "+12025550212"

    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    spent = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert spent.status_code == 429, spent.text

    resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAbudget001", "From": phone, "To": phone},
    )
    assert resp.status_code == 200
    assert "<Gather" in resp.text


async def test_webrtc_webhook_limit_is_counted_per_ip_and_answered_in_twiml(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A fresh session id per call earns no extra calls, and the 429 speaks TwiML."""
    campaign, _ = campaign_with_target
    campaign.rate_limit = 2
    await db.commit()

    responses = []
    for i in range(3):
        token_resp = await client.post(
            "/api/v1/tokens/voice",
            json={"campaign_id": str(campaign.id)},
        )
        assert token_resp.status_code == 200, token_resp.text
        session_id = token_resp.json()["session_id"]

        responses.append(
            await client.post(
                "/webhooks/twilio/voice-app",
                data={
                    "session_id": session_id,
                    "CallSid": f"CAwebrtc00{i}",
                    "From": f"client:{session_id}",
                },
            )
        )

    assert "<Gather" in responses[0].text
    assert "<Gather" in responses[1].text

    limited = responses[2]
    assert limited.status_code == 200
    assert "<Hangup" in limited.text
    assert "<Gather" not in limited.text
    assert limited.headers["content-type"].startswith("application/xml")
    assert "Too many requests" not in limited.text


# ---------------------------------------------------------------------------
# Deleting a target out from under a live call
# ---------------------------------------------------------------------------


async def test_remove_target_keeps_a_row_a_live_call_still_needs(
    client: AsyncClient,
    db: AsyncSession,
    redis,
    admin_headers: dict[str, str],
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """A target queued in a live session is detached from the campaign, not deleted."""
    campaign, target = campaign_with_target
    session_id = uuid.uuid4()

    await save_call_state(
        session_id,
        {
            "campaign_id": str(campaign.id),
            "target_ids": [str(target.id)],
            "current_target_index": 0,
            "caller_phone_hash": "",
            "connection_type": "webrtc",
            "client_ip": TEST_IP,
        },
    )

    try:
        resp = await client.delete(
            f"/api/v1/campaigns/{campaign.id}/targets/{target.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 204, resp.text
    finally:
        await redis.delete(f"call_session:{session_id}")

    still_there = await db.scalar(select(Target.id).where(Target.id == target.id))
    assert still_there == target.id

    attached = await db.scalar(
        select(func.count())
        .select_from(CampaignTarget)
        .where(CampaignTarget.target_id == target.id)
    )
    assert attached == 0


# ---------------------------------------------------------------------------
# Rep token storage and the phone-hash pepper
# ---------------------------------------------------------------------------


async def test_corrupt_rep_token_record_is_refused(
    client: AsyncClient,
    live_campaign: Campaign,
    redis,
) -> None:
    """A stored record that is not JSON resolves to nothing, and the call is a 422."""
    token = secrets.token_urlsafe(24)
    await redis.set(f"rep_token:{token}", "{not json at all", ex=60)

    try:
        assert await resolve_rep_token(token, str(live_campaign.id)) is None

        resp = await client.post(
            "/api/v1/calls/create",
            json={
                "campaign_id": str(live_campaign.id),
                "phone_number": "+12025550214",
                "rep_token": token,
            },
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["detail"]["code"] == "rep_token_invalid"
    finally:
        await redis.delete(f"rep_token:{token}")


async def test_pepper_keys_the_stored_digest_and_the_blocklist(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
    admin_headers: dict[str, str],
    redis,
    monkeypatch,
) -> None:
    """With a pepper set, sessions and blocklist entries share the same HMAC digest."""
    campaign, _ = campaign_with_target
    phone = "+12025550213"
    pepper = "pepper-for-the-security-suite"
    monkeypatch.setattr(settings, "PHONE_HASH_PEPPER", pepper)

    expected = hmac.new(pepper.encode(), phone.encode(), hashlib.sha256).hexdigest()
    assert expected != hashlib.sha256(phone.encode()).hexdigest()

    peppered_bucket = f"rate:call:{expected}"
    await redis.delete(peppered_bucket)

    try:
        resp = await client.post(
            "/api/v1/calls/create",
            json={"campaign_id": str(campaign.id), "phone_number": phone},
        )
        assert resp.status_code == 200, resp.text

        stored = await db.scalar(
            select(CallSession.caller_phone_hash).where(
                CallSession.id == uuid.UUID(resp.json()["session_id"])
            )
        )
        assert stored == expected

        block = await client.post(
            "/api/v1/admin/blocklist",
            json={"phone_number": phone, "reason": "pepper test"},
            headers=admin_headers,
        )
        assert block.status_code == 201, block.text
        assert block.json()["phone_hash"] == expected
        entry_id = block.json()["id"]

        try:
            blocked = await client.post(
                "/api/v1/calls/create",
                json={"campaign_id": str(campaign.id), "phone_number": phone},
            )
            assert blocked.status_code == 403, blocked.text
        finally:
            await db.execute(
                delete(BlocklistEntry).where(BlocklistEntry.id == uuid.UUID(entry_id))
            )
            await db.commit()
    finally:
        await redis.delete(peppered_bucket)
