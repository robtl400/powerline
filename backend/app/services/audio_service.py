"""Audio resolution service.

Resolution order for any (campaign_id, key) pair:
  1. Active AudioRecording row in DB with matching campaign_id + key
  2. YAML fallback from backend/app/defaults/audio.yml

Cloudinary upload wraps the sync SDK in run_in_executor, matching the
pattern used for the Twilio SDK throughout this codebase.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import structlog
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioRecording
from app.services.telephony.twiml import AudioConfig

log = structlog.get_logger()

# Load YAML once at module import — defaults never change at runtime.
_DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "audio.yml"

with _DEFAULTS_PATH.open() as _f:
    _DEFAULTS: dict[str, str] = yaml.safe_load(_f)


async def get_audio_config(
    key: str,
    campaign_id: uuid.UUID | None,
    db: AsyncSession,
) -> AudioConfig:
    """Return an AudioConfig for the given slot key and campaign.

    Queries the DB for an active recording first; falls back to YAML default.
    """
    if campaign_id is not None:
        result = await db.execute(
            select(AudioRecording)
            .where(
                AudioRecording.campaign_id == campaign_id,
                AudioRecording.key == key,
                AudioRecording.is_active == True,  # noqa: E712
            )
            .limit(1)
        )
        recording = result.scalar_one_or_none()

        if recording:
            return AudioConfig(
                file_url=recording.file_url or None,
                tts_text=recording.tts_text or None,
            )

    default_text = _DEFAULTS.get(key)
    if not default_text:
        log.warning("audio_key_missing_from_defaults", key=key)
    return AudioConfig(tts_text=default_text)


async def upload_audio_to_cloudinary(
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Upload audio bytes to Cloudinary and return the secure public URL.

    Cloudinary's SDK is synchronous — run it in an executor to keep the event
    loop free. The SDK is imported lazily so the server starts even if
    CLOUDINARY_* env vars are not yet configured.

    Audio files must be uploaded with resource_type="video" — Cloudinary uses
    that type for all non-image media including audio.
    """
    from app.config import settings

    def _upload() -> str:
        import cloudinary  # lazy import
        import cloudinary.uploader

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET,
        )
        # Strip extension from filename for public_id; Cloudinary appends format.
        public_id = f"powerline/audio/{filename.rsplit('.', 1)[0]}"
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp3"

        result = cloudinary.uploader.upload(
            file_bytes,
            resource_type="video",  # Cloudinary resource type for all audio
            public_id=public_id,
            format=ext,
            overwrite=True,
        )
        return result["secure_url"]

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _upload)
