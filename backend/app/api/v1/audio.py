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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser
from app.models.audio import AUDIO_KEYS, AudioRecording
from app.schemas.audio import AudioRecordingCreate, AudioRecordingResponse
from app.services.audio_service import upload_audio_to_cloudinary

router_audio = APIRouter(prefix="/audio", tags=["audio"])
router_campaign_audio = APIRouter(prefix="/campaigns", tags=["audio"])

_ALLOWED_CONTENT_TYPES = {"audio/mpeg", "audio/wav", "audio/x-wav"}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _to_response(r: AudioRecording) -> AudioRecordingResponse:
    return AudioRecordingResponse.model_validate(r)


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
) -> AudioRecordingResponse:
    """Upload an MP3 or WAV file to S3 and create an AudioRecording row.

    The new recording is NOT automatically activated — call PATCH /{id}/activate
    to make it the active version for its slot.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Only MP3 and WAV files are accepted"
        )
    if key not in AUDIO_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid audio key. Valid keys: {sorted(AUDIO_KEYS)}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File too large. Maximum size is 10 MB.")

    ext = "mp3" if "mpeg" in (file.content_type or "") else "wav"
    filename = f"{uuid.uuid4()}.{ext}"

    url = await upload_audio_to_cloudinary(file_bytes, filename, file.content_type or "audio/mpeg")

    next_version = await _next_version(db, campaign_id, key)
    recording = AudioRecording(
        campaign_id=campaign_id,
        key=key,
        version=next_version,
        file_url=url,
        description=description,
        is_active=False,
    )
    db.add(recording)
    await db.commit()
    await db.refresh(recording)
    return _to_response(recording)


# ---------------------------------------------------------------------------
# PATCH /audio/{audio_id}/activate
# ---------------------------------------------------------------------------

@router_audio.patch("/{audio_id}/activate", response_model=AudioRecordingResponse)
async def activate_audio(
    audio_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> AudioRecordingResponse:
    """Set this version as the active one for its (campaign_id, key) slot.

    Atomically deactivates all other versions for the same slot within a
    single transaction.
    """
    result = await db.execute(
        select(AudioRecording).where(AudioRecording.id == audio_id)
    )
    recording = result.scalar_one_or_none()
    if not recording:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio recording not found")

    # Deactivate all other versions for this (campaign_id, key) pair.
    await db.execute(
        update(AudioRecording)
        .where(
            AudioRecording.campaign_id == recording.campaign_id,
            AudioRecording.key == recording.key,
            AudioRecording.id != audio_id,
        )
        .values(is_active=False)
    )
    recording.is_active = True
    await db.commit()
    await db.refresh(recording)
    return _to_response(recording)


# ---------------------------------------------------------------------------
# GET /campaigns/{campaign_id}/audio
# ---------------------------------------------------------------------------

@router_campaign_audio.get("/{campaign_id}/audio", response_model=list[AudioRecordingResponse])
async def list_campaign_audio(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
) -> list[AudioRecordingResponse]:
    """List all AudioRecording rows for a campaign, ordered by key then version descending."""
    result = await db.execute(
        select(AudioRecording)
        .where(AudioRecording.campaign_id == campaign_id)
        .order_by(AudioRecording.key, AudioRecording.version.desc())
        .offset(skip)
        .limit(limit)
    )
    return [_to_response(r) for r in result.scalars().all()]


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
) -> AudioRecordingResponse:
    """Create a new TTS AudioRecording version for a campaign+key pair.

    For file uploads use POST /audio/upload instead — this endpoint is
    TTS-text-only. The new version is inactive until PATCH /{id}/activate.
    """
    if body.key not in AUDIO_KEYS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid audio key. Valid keys: {sorted(AUDIO_KEYS)}",
        )

    next_version = await _next_version(db, campaign_id, body.key)
    recording = AudioRecording(
        campaign_id=campaign_id,
        key=body.key,
        version=next_version,
        tts_text=body.tts_text,
        description=body.description,
        is_active=False,
    )
    db.add(recording)
    await db.commit()
    await db.refresh(recording)
    return _to_response(recording)
