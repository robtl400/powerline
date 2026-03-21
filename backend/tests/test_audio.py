"""Tests for audio upload, MIME type validation, and live campaign guard."""

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioRecording
from app.models.campaign import Campaign
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_URL = "https://res.cloudinary.com/test/audio/upload/test.mp3"


def _audio_file(content_type: str, filename: str = "test.mp3") -> dict:
    return {
        "file": (filename, io.BytesIO(b"FAKE_AUDIO_DATA"), content_type),
    }


@pytest.fixture
async def live_campaign(db: AsyncSession, admin_user: User):
    c = Campaign(
        name=f"Live Campaign {uuid.uuid4().hex[:8]}",
        status="live",
        created_by_id=admin_user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    yield c
    await db.execute(delete(AudioRecording).where(AudioRecording.campaign_id == c.id))
    await db.execute(delete(Campaign).where(Campaign.id == c.id))
    await db.commit()


@pytest.fixture
async def paused_campaign(db: AsyncSession, admin_user: User):
    c = Campaign(
        name=f"Paused Campaign {uuid.uuid4().hex[:8]}",
        status="paused",
        created_by_id=admin_user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    yield c
    await db.execute(delete(AudioRecording).where(AudioRecording.campaign_id == c.id))
    await db.execute(delete(Campaign).where(Campaign.id == c.id))
    await db.commit()


# ---------------------------------------------------------------------------
# Upload: MIME type validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content_type,filename", [
    ("audio/mpeg",   "test.mp3"),
    ("audio/wav",    "test.wav"),
    ("audio/x-wav",  "test.wav"),
    ("audio/webm",   "test.webm"),
    ("audio/mp4",    "test.m4a"),
])
async def test_upload_accepted_mime_types(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
    content_type: str,
    filename: str,
) -> None:
    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ):
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "msg_intro", "campaign_id": str(campaign.id)},
            files=_audio_file(content_type, filename),
            headers=admin_headers,
        )
    assert resp.status_code == 201, resp.text


async def test_upload_rejected_mime_type(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    resp = await client.post(
        "/api/v1/audio/upload",
        data={"key": "msg_intro", "campaign_id": str(campaign.id)},
        files=_audio_file("video/mp4", "test.mp4"),
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Activate: live campaign guard
# ---------------------------------------------------------------------------

async def _create_recording(
    db: AsyncSession, campaign_id: uuid.UUID, key: str = "msg_intro"
) -> AudioRecording:
    rec = AudioRecording(
        campaign_id=campaign_id,
        key=key,
        version=1,
        file_url=_FAKE_URL,
        is_active=False,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return rec


async def test_activate_blocked_when_live(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
    admin_headers: dict,
) -> None:
    rec = await _create_recording(db, live_campaign.id)
    resp = await client.patch(
        f"/api/v1/audio/{rec.id}/activate",
        headers=admin_headers,
    )
    assert resp.status_code == 409
    assert "Pause" in resp.json()["detail"]


async def test_activate_allowed_when_paused(
    client: AsyncClient,
    db: AsyncSession,
    paused_campaign: Campaign,
    admin_headers: dict,
) -> None:
    rec = await _create_recording(db, paused_campaign.id)
    resp = await client.patch(
        f"/api/v1/audio/{rec.id}/activate",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


# ---------------------------------------------------------------------------
# Upload: additional validation
# ---------------------------------------------------------------------------

async def test_upload_file_too_large(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    large_data = b"x" * (10 * 1024 * 1024 + 1)
    resp = await client.post(
        "/api/v1/audio/upload",
        data={"key": "msg_intro", "campaign_id": str(campaign.id)},
        files={"file": ("big.mp3", io.BytesIO(large_data), "audio/mpeg")},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_upload_invalid_key(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ):
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "not_a_real_key", "campaign_id": str(campaign.id)},
            files=_audio_file("audio/mpeg"),
            headers=admin_headers,
        )
    assert resp.status_code == 422


async def test_upload_no_campaign(
    client: AsyncClient,
    admin_headers: dict,
) -> None:
    """Upload without a campaign_id (global audio) should succeed."""
    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ):
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "msg_intro"},
            files=_audio_file("audio/mpeg"),
            headers=admin_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["campaign_id"] is None


# ---------------------------------------------------------------------------
# Activate: additional edge cases
# ---------------------------------------------------------------------------

async def test_activate_not_found(
    client: AsyncClient,
    admin_headers: dict,
) -> None:
    resp = await client.patch(
        f"/api/v1/audio/{uuid.uuid4()}/activate",
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_activate_deactivates_previous(
    client: AsyncClient,
    db: AsyncSession,
    paused_campaign: Campaign,
    admin_headers: dict,
) -> None:
    """Activating a version atomically deactivates the previously active one."""
    v1 = AudioRecording(
        campaign_id=paused_campaign.id,
        key="msg_intro",
        version=1,
        file_url=_FAKE_URL,
        is_active=True,
    )
    v2 = AudioRecording(
        campaign_id=paused_campaign.id,
        key="msg_intro",
        version=2,
        file_url=_FAKE_URL,
        is_active=False,
    )
    db.add(v1)
    db.add(v2)
    await db.commit()
    await db.refresh(v1)
    await db.refresh(v2)

    resp = await client.patch(
        f"/api/v1/audio/{v2.id}/activate",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    await db.refresh(v1)
    assert v1.is_active is False


async def test_activate_global_recording(
    client: AsyncClient,
    db: AsyncSession,
    admin_headers: dict,
) -> None:
    """A recording with no campaign_id (global) can be activated."""
    rec = AudioRecording(
        campaign_id=None,
        key="msg_intro",
        version=1,
        file_url=_FAKE_URL,
        is_active=False,
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    resp = await client.patch(
        f"/api/v1/audio/{rec.id}/activate",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True

    await db.execute(delete(AudioRecording).where(AudioRecording.id == rec.id))
    await db.commit()
