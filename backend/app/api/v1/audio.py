"""Audio management endpoints.

Two routers are exported so main.py can mount them independently:
  router_audio          prefix /audio    — upload + activate
  router_campaign_audio prefix /campaigns — list + create-TTS

Route ordering within router_audio:
  POST /audio/upload is a literal path — FastAPI resolves it before
  PATCH /audio/{audio_id}/activate (parameterized), so no conflict.
  If a GET /audio/{id} is added later, register it AFTER the PATCH.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, CurrentUser
from app.api.v1.helpers import read_upload_limited
from app.models.audio import AUDIO_KEYS, AudioRecording
from app.models.campaign import Campaign
from app.schemas.audio import AudioRecordingCreate, AudioRecordingResponse
from app.services.audio_service import upload_audio_to_cloudinary

router_audio = APIRouter(prefix="/audio", tags=["audio"])
router_campaign_audio = APIRouter(prefix="/campaigns", tags=["audio"])

_ALLOWED_CONTENT_TYPES = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/webm", "audio/mp4"}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_VERSION_ATTEMPTS = 3
_CONTENT_MISMATCH = "File content does not match an accepted audio format"


def _looks_like_audio(head: bytes) -> bool:
    """True when the leading bytes match MP3, WAV, WebM or MP4/M4A.

    A declared content type is caller-supplied and proves nothing, so the file's
    own header decides whether it reaches storage.
    """
    if head[:3] == b"ID3":
        return True
    if len(head) >= 2 and head[0] == 0xFF and head[1] in (0xFB, 0xF3, 0xF2):
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return True
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return True
    if head[4:8] == b"ftyp":
        return True
    return False


async def _next_version(
    db: AsyncSession, campaign_id: uuid.UUID | None, key: str
) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(AudioRecording.version), 0)).where(
            AudioRecording.campaign_id == campaign_id,
            AudioRecording.key == key,
        )
    )
    return result.scalar_one() + 1


async def _insert_versioned(
    db: AsyncSession,
    campaign_id: uuid.UUID | None,
    key: str,
    **fields,
) -> AudioRecording:
    """Insert a recording at the next free version for its slot.

    Two concurrent uploads can pick the same version number; the slot's unique
    constraint catches that and the losing insert re-reads the maximum and
    retries.
    """
    for _ in range(_MAX_VERSION_ATTEMPTS):
        recording = AudioRecording(
            campaign_id=campaign_id,
            key=key,
            version=await _next_version(db, campaign_id, key),
            is_active=False,
            **fields,
        )
        db.add(recording)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue
        await db.refresh(recording)
        return recording

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Another version was created at the same time. Please try again.",
    )


# ---------------------------------------------------------------------------
# POST /audio/upload
# ---------------------------------------------------------------------------

@router_audio.post("/upload", response_model=AudioRecordingResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    _: AdminUser,
    db: DB,
    key: str = Form(...),
    file: UploadFile = File(...),
    campaign_id: uuid.UUID | None = Form(default=None),
    description: str | None = Form(default=None),
) -> AudioRecording:
    """Upload an MP3 or WAV file to S3 and create an AudioRecording row.

    The new recording is NOT automatically activated — call PATCH /{id}/activate
    to make it the active version for its slot.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Accepted formats: MP3, WAV, WebM, MP4 (max 10 MB)"
        )
    if key not in AUDIO_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid audio key. Valid keys: {sorted(AUDIO_KEYS)}",
        )

    file_bytes = await read_upload_limited(file, _MAX_FILE_BYTES)
    if file_bytes is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File too large. Maximum size is 10 MB.")

    if not _looks_like_audio(file_bytes[:16]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_CONTENT_MISMATCH
        )

    ext_map = {"mpeg": "mp3", "wav": "wav", "x-wav": "wav", "webm": "webm", "mp4": "m4a"}
    subtype = (file.content_type or "").split("/")[-1]
    ext = ext_map.get(subtype, "mp3")
    filename = f"{uuid.uuid4()}.{ext}"

    url = await upload_audio_to_cloudinary(file_bytes, filename, file.content_type or "audio/mpeg")

    return await _insert_versioned(
        db, campaign_id, key, file_url=url, description=description
    )


# ---------------------------------------------------------------------------
# PATCH /audio/{audio_id}/activate
# ---------------------------------------------------------------------------

@router_audio.patch("/{audio_id}/activate", response_model=AudioRecordingResponse)
async def activate_audio(
    audio_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> AudioRecording:
    """Set this version as the active one for its (campaign_id, key) slot.

    The slot's rows are locked for the duration, so two concurrent activations
    serialize instead of racing the partial unique index that allows only one
    active version per slot.
    """
    result = await db.execute(
        select(AudioRecording).where(AudioRecording.id == audio_id)
    )
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio recording not found")

    # Block activation on live campaigns.
    if recording.campaign_id:
        campaign_result = await db.execute(
            select(Campaign).where(Campaign.id == recording.campaign_id)
        )
        campaign = campaign_result.scalar_one_or_none()
        if campaign and campaign.status == "live":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pause the campaign before changing audio",
            )

    slot = (
        AudioRecording.campaign_id == recording.campaign_id,
        AudioRecording.key == recording.key,
    )
    await db.execute(select(AudioRecording.id).where(*slot).with_for_update())
    await db.execute(
        update(AudioRecording)
        .where(*slot, AudioRecording.id != audio_id)
        .values(is_active=False)
    )
    recording.is_active = True
    await db.commit()
    await db.refresh(recording)
    return recording


# ---------------------------------------------------------------------------
# GET /campaigns/{campaign_id}/audio
# ---------------------------------------------------------------------------

@router_campaign_audio.get("/{campaign_id}/audio", response_model=list[AudioRecordingResponse])
async def list_campaign_audio(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
) -> list[AudioRecording]:
    """List all AudioRecording rows for a campaign, ordered by key then version descending."""
    result = await db.execute(
        select(AudioRecording)
        .where(AudioRecording.campaign_id == campaign_id)
        .order_by(AudioRecording.key, AudioRecording.version.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# POST /campaigns/{campaign_id}/audio  (TTS-only; file upload uses /audio/upload)
# ---------------------------------------------------------------------------

@router_campaign_audio.post(
    "/{campaign_id}/audio", response_model=AudioRecordingResponse, status_code=status.HTTP_201_CREATED
)
async def create_audio(
    campaign_id: uuid.UUID,
    body: AudioRecordingCreate,
    _: AdminUser,
    db: DB,
) -> AudioRecording:
    """Create a new TTS AudioRecording version for a campaign+key pair.

    For file uploads use POST /audio/upload instead — this endpoint is
    TTS-text-only. The new version is inactive until PATCH /{id}/activate.
    """
    if body.key not in AUDIO_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid audio key. Valid keys: {sorted(AUDIO_KEYS)}",
        )

    return await _insert_versioned(
        db, campaign_id, body.key, tts_text=body.tts_text, description=body.description
    )
