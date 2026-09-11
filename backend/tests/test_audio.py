"""Tests for audio upload, MIME type validation, and live campaign guard."""

import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioRecording
from app.models.campaign import Campaign
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_URL = "https://res.cloudinary.com/test/audio/upload/test.mp3"

# Leading bytes the upload endpoint sniffs for, one per accepted container.
_HEADERS: dict[str, bytes] = {
    "audio/mpeg": b"ID3\x04\x00\x00\x00\x00\x00\x00",
    "audio/wav": b"RIFF\x24\x00\x00\x00WAVEfmt ",
    "audio/x-wav": b"RIFF\x24\x00\x00\x00WAVEfmt ",
    "audio/webm": b"\x1a\x45\xdf\xa3\x01\x00\x00\x00",
    "audio/mp4": b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00",
}


def _audio_bytes(content_type: str) -> bytes:
    return _HEADERS.get(content_type, _HEADERS["audio/mpeg"]) + b"FAKE_AUDIO_DATA"


def _audio_file(content_type: str, filename: str = "test.mp3") -> dict:
    return {
        "file": (filename, io.BytesIO(_audio_bytes(content_type)), content_type),
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


async def test_upload_rejects_content_not_matching_audio_header(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    """An accepted MIME type with a non-audio payload is rejected on its bytes."""
    resp = await client.post(
        "/api/v1/audio/upload",
        data={"key": "msg_intro", "campaign_id": str(campaign.id)},
        files={"file": ("test.mp3", io.BytesIO(b"%PDF-1.7 not audio at all"), "audio/mpeg")},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert "does not match an accepted audio format" in resp.json()["detail"]


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
    large_data = _audio_bytes("audio/mpeg") + b"x" * (10 * 1024 * 1024)
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


async def test_upload_without_a_campaign_is_rejected(
    client: AsyncClient,
    admin_headers: dict,
) -> None:
    """A recording is only ever resolved for a campaign, so the field is required."""
    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ) as upload:
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "msg_intro"},
            files=_audio_file("audio/mpeg"),
            headers=admin_headers,
        )
    assert resp.status_code == 422
    assert "campaign_id" in resp.text
    upload.assert_not_awaited()


@pytest.mark.parametrize("head,accepted", [
    (b"\xff\xfb\x90\x64\x00\x00\x00\x00", True),
    (b"\xff\xf3\x90\x64\x00\x00\x00\x00", True),
    (b"\xff\xf2\x90\x64\x00\x00\x00\x00", True),
    (b"\xff", False),
    (b"", False),
    (b"\xff\x00", False),
])
def test_looks_like_audio_reads_the_mp3_frame_sync(head: bytes, accepted: bool) -> None:
    """A frameless MP3 is accepted on its sync word; a truncated header is not."""
    from app.api.v1.audio import _looks_like_audio

    assert _looks_like_audio(head) is accepted


async def test_upload_accepts_a_frame_sync_mp3(
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
            data={"key": "msg_intro", "campaign_id": str(campaign.id)},
            files={"file": ("test.mp3", io.BytesIO(b"\xff\xfb\x90\x64" + b"\x00" * 64), "audio/mpeg")},
            headers=admin_headers,
        )
    assert resp.status_code == 201, resp.text


async def test_upload_reports_409_when_every_version_insert_collides(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    """Losing the version race on every attempt is a conflict, not a 500."""
    collision = IntegrityError(
        "INSERT",
        {},
        Exception('duplicate key value violates unique constraint "uq_audio_recordings_campaign_key_version"'),
    )

    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ), patch.object(AsyncSession, "commit", AsyncMock(side_effect=collision)):
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "msg_intro", "campaign_id": str(campaign.id)},
            files=_audio_file("audio/mpeg"),
            headers=admin_headers,
        )

    assert resp.status_code == 409, resp.text
    assert "same time" in resp.json()["detail"]


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


# ---------------------------------------------------------------------------
# The campaign is settled before anything is uploaded or inserted
# ---------------------------------------------------------------------------


async def test_upload_to_an_unknown_campaign_is_404_before_the_upload(
    client: AsyncClient,
    admin_headers: dict,
) -> None:
    """No Cloudinary object is created for a campaign that does not exist."""
    cloudinary = AsyncMock(return_value=_FAKE_URL)

    with patch("app.api.v1.audio.upload_audio_to_cloudinary", cloudinary):
        resp = await client.post(
            "/api/v1/audio/upload",
            data={"key": "msg_intro", "campaign_id": str(uuid.uuid4())},
            files=_audio_file("audio/mpeg"),
            headers=admin_headers,
        )

    assert resp.status_code == 404, resp.text
    cloudinary.assert_not_awaited()


async def test_create_tts_for_an_unknown_campaign_is_404(
    client: AsyncClient,
    admin_headers: dict,
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{uuid.uuid4()}/audio",
        json={"key": "msg_intro", "tts_text": "Hello"},
        headers=admin_headers,
    )
    assert resp.status_code == 404, resp.text


async def test_upload_does_not_retry_an_unrelated_integrity_error(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    """Only a version collision is a race; anything else is raised, not retried."""
    unrelated = IntegrityError(
        "INSERT",
        {},
        Exception(
            'insert or update on table "audio_recordings" violates foreign key '
            'constraint "audio_recordings_campaign_id_fkey"'
        ),
    )

    with patch(
        "app.api.v1.audio.upload_audio_to_cloudinary",
        new_callable=AsyncMock,
        return_value=_FAKE_URL,
    ), patch.object(AsyncSession, "commit", AsyncMock(side_effect=unrelated)):
        with pytest.raises(IntegrityError):
            await client.post(
                "/api/v1/audio/upload",
                data={"key": "msg_intro", "campaign_id": str(campaign.id)},
                files=_audio_file("audio/mpeg"),
                headers=admin_headers,
            )
