"""Tests for the WebRTC voice token endpoint and WebRTC call flow.

Covers:
  - POST /api/v1/tokens/voice returns {token, session_id} and persists CallSession
  - Full WebRTC path: tokens/voice → voice-app webhook → <Gather> TwiML
  - Rate limit: 6th token request from same IP returns 429
"""
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target


@pytest.fixture(autouse=True)
def mock_build_access_token():
    """Skip real Twilio JWT signing — return a stable dev token string."""
    with patch("app.api.v1.tokens._build_access_token", return_value="dev-token"):
        yield


@pytest.fixture(autouse=True)
async def clear_token_rate_limit(redis):
    """Drop the shared per-IP token bucket around every test in this module.

    Every request from the ASGI test client arrives from the same client IP,
    so the "token" bucket would otherwise leak between tests.
    """
    await redis.delete("rate:token:127.0.0.1")
    yield
    await redis.delete("rate:token:127.0.0.1")


@pytest.fixture
async def live_webrtc_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    """Promote the shared campaign fixture to live with WebRTC enabled."""
    campaign.status = "live"
    campaign.allow_webrtc = True
    campaign.rate_limit = 5
    await db.commit()
    await db.refresh(campaign)
    return campaign


@pytest.fixture
async def webrtc_campaign_with_target(
    db: AsyncSession, live_webrtc_campaign: Campaign
) -> tuple[Campaign, Target]:
    """Add one target to the live WebRTC campaign."""
    target = Target(
        name="Test Rep",
        phone_number="+15550002222",
        title="Representative",
        location="WA",
    )
    db.add(target)
    await db.flush()

    ct = CampaignTarget(
        campaign_id=live_webrtc_campaign.id, target_id=target.id, order=0
    )
    db.add(ct)
    await db.commit()

    target_id = target.id
    campaign_id = live_webrtc_campaign.id

    yield live_webrtc_campaign, target

    await db.execute(delete(Call).where(Call.target_id == target_id))
    await db.execute(delete(CallSession).where(CallSession.campaign_id == campaign_id))
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target_id))
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


# ---------------------------------------------------------------------------
# WebRTC token endpoint
# ---------------------------------------------------------------------------


async def test_tokens_voice_returns_session(
    client: AsyncClient,
    db: AsyncSession,
    webrtc_campaign_with_target: tuple[Campaign, Target],
) -> None:
    """POST /tokens/voice returns {token, session_id} and persists CallSession."""
    campaign, _ = webrtc_campaign_with_target

    response = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(campaign.id)},
    )
    assert response.status_code == 200, response.text

    data = response.json()
    assert "token" in data
    assert "session_id" in data

    session_id = uuid.UUID(data["session_id"])
    result = await db.execute(select(CallSession).where(CallSession.id == session_id))
    session = result.scalar_one_or_none()
    assert session is not None
    assert session.status == "initiated"
    assert session.connection_type == "webrtc"
    assert session.campaign_id == campaign.id


# ---------------------------------------------------------------------------
# WebRTC end-to-end path: tokens/voice → voice-app
# ---------------------------------------------------------------------------


async def test_webrtc_voice_app_returns_gather_twiml(
    client: AsyncClient,
    db: AsyncSession,
    webrtc_campaign_with_target: tuple[Campaign, Target],
) -> None:
    """Full WebRTC smoke: token → voice-app → <Gather> TwiML, session in_progress."""
    campaign, _ = webrtc_campaign_with_target

    # Step 1: widget requests a token (WebRTC path)
    token_resp = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(campaign.id)},
    )
    assert token_resp.status_code == 200, token_resp.text
    session_id = token_resp.json()["session_id"]

    # Step 2: simulate Twilio calling voice-app (WebRTC path sends session_id in body)
    webhook_resp = await client.post(
        "/webhooks/twilio/voice-app",
        data={
            "session_id": session_id,
            "CallSid": "CAwebrtc0001",
            "From": f"client:{session_id}",
        },
    )
    assert webhook_resp.status_code == 200, webhook_resp.text
    assert webhook_resp.headers["content-type"] == "application/xml"

    xml = webhook_resp.text
    assert "<Gather" in xml, f"Expected <Gather> in TwiML:\n{xml}"

    # Verify DB: session advanced to in_progress with the Twilio CallSid.
    result = await db.execute(
        select(CallSession).where(CallSession.id == uuid.UUID(session_id))
    )
    session = result.scalar_one()
    assert session.status == "in_progress"
    assert session.twilio_call_sid == "CAwebrtc0001"


# ---------------------------------------------------------------------------
# Rate limit: POST /tokens/voice (IP-based, limit = 5/hour)
# ---------------------------------------------------------------------------


async def test_rate_limit_tokens_voice(
    client: AsyncClient,
    db: AsyncSession,
    webrtc_campaign_with_target: tuple[Campaign, Target],
    redis,
) -> None:
    """6th token request from the same IP within an hour returns 429."""
    campaign, _ = webrtc_campaign_with_target

    for i in range(5):
        resp = await client.post(
            "/api/v1/tokens/voice",
            json={"campaign_id": str(campaign.id)},
        )
        assert resp.status_code == 200, f"Call {i + 1} expected 200, got {resp.status_code}: {resp.text}"

    resp = await client.post(
        "/api/v1/tokens/voice",
        json={"campaign_id": str(campaign.id)},
    )
    assert resp.status_code == 429, f"Expected 429 on 6th token request, got {resp.status_code}"
