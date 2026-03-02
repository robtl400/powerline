"""Smoke tests for the phone callback call creation flow.

Tests the full path from POST /api/v1/calls/create through the
voice-app webhook, verifying TwiML is returned correctly.

Twilio outbound call is mocked so tests never hit the real Twilio API,
regardless of whether TWILIO_ACCOUNT_SID / PUBLIC_BASE_URL are set in .env.
Redis must be reachable (provided by docker compose).
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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


@pytest.fixture
async def live_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    """Promote the shared campaign fixture to live with phone callback enabled."""
    campaign.status = "live"
    campaign.allow_phone_callback = True
    campaign.lookup_validate = False  # skip Twilio Lookup in tests
    campaign.rate_limit = None  # unlimited — no Redis rate-limit ops
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
            "phone_number": "+15559876543",
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
            "phone_number": "+15559876544",
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    session_id = create_resp.json()["session_id"]

    # Step 2: simulate Twilio calling voice-app (phone callback path uses query param)
    webhook_resp = await client.post(
        f"/webhooks/twilio/voice-app?session_id={session_id}",
        data={"CallSid": "CAsmoke0001", "From": "+15559876544"},
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
            "phone_number": "+15559876545",
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
            "phone_number": "+15559876546",
        },
    )
    assert response.status_code == 422

    # Restore for fixture cleanup
    live_campaign.allow_phone_callback = True
    await db.commit()
