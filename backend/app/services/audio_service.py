"""Audio resolution service.

Resolution order for any (campaign_id, key) pair:
  1. Active AudioRecording row in DB with matching campaign_id + key
  2. Fallback from backend/app/defaults/audio.json

Cloudinary upload wraps the sync SDK in run_in_executor, matching the
pattern used for the Twilio SDK throughout this codebase.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Iterable
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioRecording
from app.services.telephony.twiml import AudioConfig

log = structlog.get_logger()

# Load once at module import — defaults never change at runtime.
_DEFAULTS_PATH = Path(__file__).parent.parent / "defaults" / "audio.json"

with _DEFAULTS_PATH.open() as _f:
    _DEFAULTS: dict[str, str] = json.load(_f)


async def get_audio_config(
    key: str,
    campaign_id: uuid.UUID | None,
    db: AsyncSession,
) -> AudioConfig:
    """Return an AudioConfig for the given slot key and campaign.

    Queries the DB for an active recording first; falls back to the file default.
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

    return _default_config(key)


async def get_audio_configs(
    keys: Iterable[str],
    campaign_id: uuid.UUID | None,
    db: AsyncSession,
) -> dict[str, AudioConfig]:
    """Return an AudioConfig per requested slot key, loaded in one query.

    A handler that plays more than one slot reads every active recording it
    needs together instead of one SELECT per slot. Each key resolves the same
    way get_audio_config resolves a single one: the campaign's active recording
    if there is one, the file default otherwise.
    """
    wanted = list(dict.fromkeys(keys))
    recordings: dict[str, AudioRecording] = {}

    if campaign_id is not None and wanted:
        result = await db.execute(
            select(AudioRecording).where(
                AudioRecording.campaign_id == campaign_id,
                AudioRecording.key.in_(wanted),
                AudioRecording.is_active == True,  # noqa: E712
            )
        )
        for recording in result.scalars():
            recordings.setdefault(recording.key, recording)

    configs: dict[str, AudioConfig] = {}
    for key in wanted:
        recording = recordings.get(key)
        if recording:
            configs[key] = AudioConfig(
                file_url=recording.file_url or None,
                tts_text=recording.tts_text or None,
            )
        else:
            configs[key] = _default_config(key)
    return configs


def _default_config(key: str) -> AudioConfig:
    """Return the file default for a slot key, warning when there is none."""
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
