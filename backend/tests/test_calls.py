"""Smoke tests for the phone callback call creation flow.

Tests the full path from POST /api/v1/calls/create through the
voice-app webhook, verifying TwiML is returned correctly.

Twilio outbound call is mocked so tests never hit the real Twilio API,
regardless of whether TWILIO_ACCOUNT_SID / PUBLIC_BASE_URL are set in .env.
Redis must be reachable (provided by docker compose).
"""
import hashlib
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.telephony.base import CallResult


@pytest.fixture(autouse=True)
def mock_twilio_create_call():
    """Patch get_provider() in calls.py so no real Twilio API calls are made.

    Uses autouse=True so every test in this module gets the mock automatically,
    regardless of whether credentials are present in .env.
    """
    mock_provider = MagicMock()
    mock_provider.create_call.return_value = CallResult(sid="CAtest", status="queued")
    mock_provider.validate_phone.return_value = MagicMock(is_valid=True, line_type="mobile")
    with patch("app.api.v1.calls.get_provider", return_value=mock_provider):
        yield mock_provider


MODULE_PHONES = [
    "+12025550143",
    "+12025550144",
    "+12025550145",
    "+12025550146",
    "+12025550171",
    "+12025550181",
    "+12025550182",
    "+12025550183",
]


@pytest.fixture(autouse=True)
async def clear_rate_buckets(redis):
    """Drop every rate-limit bucket this module touches, before and after.

    All requests from the ASGI test client share one client IP, and the
    per-phone buckets survive the hour-long window, so both would otherwise
    leak between tests and between suite runs.
    """
    keys = ["rate:call-ip:127.0.0.1"] + [
        f"rate:call:{hashlib.sha256(phone.encode()).hexdigest()}" for phone in MODULE_PHONES
    ]
    await redis.delete(*keys)
    yield
    await redis.delete(*keys)


@pytest.fixture
async def live_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    """Promote the shared campaign fixture to live with phone callback enabled."""
    campaign.status = "live"
    campaign.allow_phone_callback = True
    campaign.lookup_validate = False  # skip Twilio Lookup in tests
    campaign.rate_limit = 5
    await db.commit()
    await db.refresh(campaign)
    return campaign


@pytest.fixture
async def campaign_with_target(
    db: AsyncSession, live_campaign: Campaign
) -> tuple[Campaign, Target]:
    """Add one target to the live campaign."""
    target = Target(
        name="Test Senator",
        phone_number="+15550001111",
        title="Senator",
        location="WA",
    )
    db.add(target)
    await db.flush()

    ct = CampaignTarget(campaign_id=live_campaign.id, target_id=target.id, order=0)
    db.add(ct)
    await db.commit()

    # Capture IDs before yield — ORM objects may be expired during test execution.
    target_id = target.id
    campaign_id = live_campaign.id

    yield live_campaign, target

    # Cleanup in FK-safe order
    await db.execute(delete(Call).where(Call.target_id == target_id))
    await db.execute(delete(CallSession).where(CallSession.campaign_id == campaign_id))
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target_id))
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


async def test_create_call_returns_session(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """POST /api/v1/calls/create returns session_id and persists CallSession."""
    campaign, _ = campaign_with_target

    response = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(campaign.id),
            "phone_number": "+12025550143",
        },
    )
    assert response.status_code == 200, response.text

    data = response.json()
    assert "session_id" in data
    assert data["status"] == "initiated"

    session_id = uuid.UUID(data["session_id"])
    result = await db.execute(select(CallSession).where(CallSession.id == session_id))
    session = result.scalar_one_or_none()
    assert session is not None
    assert session.status == "initiated"
    assert session.connection_type == "outbound_phone"
    assert session.campaign_id == campaign.id


async def test_voice_app_returns_gather_twiml(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Full smoke: create call then hit voice-app — expect TwiML with <Gather>."""
    campaign, _ = campaign_with_target

    # Step 1: create session
    create_resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(campaign.id),
            "phone_number": "+12025550144",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    # Step 2: simulate Twilio calling voice-app (phone callback path uses query param)
    webhook_resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAsmoke0001", "From": "+12025550144", "To": "+12025550144"},
    )
    assert webhook_resp.status_code == 200, webhook_resp.text
    assert webhook_resp.headers["content-type"] == "application/xml"

    # Response must contain a Gather (waiting for keypress 1)
    xml = webhook_resp.text
    assert "<Gather" in xml, f"Expected <Gather> in TwiML:\n{xml}"

    # Verify DB was updated: session now in_progress with the call SID.
    # A fresh SELECT sees the committed data from the webhook handler's session
    # (NullPool + READ COMMITTED isolation). No expire_all() needed.
    result = await db.execute(
        select(CallSession).where(CallSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one()
    assert session.status == "in_progress"
    assert session.twilio_call_sid == "CAsmoke0001"


async def test_create_call_rejects_nonlive_campaign(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,  # fixture is in "draft" status
) -> None:
    """Campaign in draft status returns 404."""
    response = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(campaign.id),
            "phone_number": "+12025550145",
        },
    )
    assert response.status_code == 404


async def test_create_call_rejects_callback_disabled(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
) -> None:
    """Campaign with allow_phone_callback=False returns 422."""
    live_campaign.allow_phone_callback = False
    await db.commit()

    response = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(live_campaign.id),
            "phone_number": "+12025550146",
        },
    )
    assert response.status_code == 422

    # Restore for fixture cleanup
    live_campaign.allow_phone_callback = True
    await db.commit()


# ---------------------------------------------------------------------------
# Rate limit: POST /calls/create (phone-hash-based, per campaign.rate_limit)
# ---------------------------------------------------------------------------


@pytest.fixture
async def rate_limited_campaign(
    db: AsyncSession, campaign_with_target: tuple[Campaign, Target]
) -> Campaign:
    """Set rate_limit=5 on the shared campaign so rate limiting is enforced."""
    campaign, _ = campaign_with_target
    campaign.rate_limit = 5
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def test_rate_limit_calls_create(
    client: AsyncClient,
    db: AsyncSession,
    rate_limited_campaign: Campaign,
) -> None:
    """6th call from the same phone number within an hour returns 429."""
    phone = "+12025550171"

    for i in range(5):
        resp = await client.post(
            "/api/v1/calls/create",
            json={
                "campaign_id": str(rate_limited_campaign.id),
                "phone_number": phone,
            },
        )
        assert resp.status_code == 200, (
            f"Call {i + 1} expected 200, got {resp.status_code}: {resp.text}"
        )

    resp = await client.post(
        "/api/v1/calls/create",
        json={
            "campaign_id": str(rate_limited_campaign.id),
            "phone_number": phone,
        },
    )
    assert resp.status_code == 429, f"Expected 429 on 6th call, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Task 4: Call failure statuses written correctly by call-complete webhook
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dial_status,expected_db_status,phone,call_sid",
    [
        ("no-answer", "no_answer", "+12025550181", "CAfailtest001"),
        ("busy", "busy", "+12025550182", "CAfailtest002"),
        ("failed", "failed", "+12025550183", "CAfailtest003"),
    ],
)
async def test_call_complete_writes_failure_statuses(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
    dial_status: str,
    expected_db_status: str,
    phone: str,
    call_sid: str,
) -> None:
    """call-complete webhook correctly writes no_answer/busy/failed to the calls table.

    Failure rate = (calls.status IN ('failed', 'no_answer')) / total calls.
    This test verifies the numerator values are persisted accurately.
    """
    campaign, target = campaign_with_target

    # Step 1: create session
    create_resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    # Step 2: advance to in_progress via voice-app (phone callback path)
    va_resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": call_sid, "From": phone, "To": phone},
    )
    assert va_resp.status_code == 200, va_resp.text

    # Step 3: call-complete with the target failure status
    cc_resp = await client.post(
        f"/webhooks/twilio/call-complete?session_id={session_id}",
        data={
            "CallSid": call_sid,
            "DialCallSid": f"CAleg-{call_sid}",
            "DialCallStatus": dial_status,
            "DialCallDuration": "0",
        },
    )
    assert cc_resp.status_code == 200, cc_resp.text

    # Verify the Call record has the correct status.
    result = await db.execute(
        select(Call).where(Call.session_id == uuid.UUID(session_id))
    )
    call = result.scalar_one_or_none()
    assert call is not None, "Expected a Call record to be created"
    assert call.status == expected_db_status, (
        f"DialCallStatus '{dial_status}' should map to Call.status '{expected_db_status}', "
        f"got '{call.status}'"
    )


@pytest.mark.parametrize("line_type", ["landline", "voip", "nonFixedVoip", "tollFree", None])
async def test_lookup_require_mobile_rejects_non_mobile_lines(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
    mock_twilio_create_call: MagicMock,
    monkeypatch,
    line_type: str | None,
) -> None:
    """Only a line Twilio calls "mobile" passes when a campaign demands one."""
    campaign, _ = campaign_with_target
    campaign.lookup_validate = True
    campaign.lookup_require_mobile = True
    await db.commit()

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACtest")
    mock_twilio_create_call.validate_phone.return_value = MagicMock(
        is_valid=True, line_type=line_type
    )

    resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": "+12025550171"},
    )
    assert resp.status_code == 422, resp.text
    assert "Landline numbers cannot receive automated calls" in resp.json()["detail"]


async def test_lookup_require_mobile_allows_mobile(
    client: AsyncClient,
    db: AsyncSession,
    campaign_with_target: tuple[Campaign, Target],
    mock_twilio_create_call: MagicMock,
    monkeypatch,
) -> None:
    campaign, _ = campaign_with_target
    campaign.lookup_validate = True
    campaign.lookup_require_mobile = True
    await db.commit()

    monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", "ACtest")
    mock_twilio_create_call.validate_phone.return_value = MagicMock(
        is_valid=True, line_type="mobile"
    )

    resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": "+12025550181"},
    )
    assert resp.status_code == 200, resp.text
