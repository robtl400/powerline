"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.civic_service import resolve_rep_token

UPLOAD_CHUNK_BYTES = 64 * 1024


def local_timezone() -> ZoneInfo:
    """The reporting timezone that defines a calendar day for dashboards and filters.

    Read at call time rather than at import so a settings change takes effect
    without a reload.
    """
    return ZoneInfo(settings.TIMEZONE)


async def read_upload_limited(file: UploadFile, limit: int) -> bytes | None:
    """Read an upload in 64 KiB chunks, returning None once it exceeds `limit`.

    Reading stops at the first chunk that pushes the running total past the
    limit, so an oversized upload never occupies more than limit + one chunk
    of memory and the caller can answer without buffering the whole body.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)


async def get_campaign_or_404(campaign_id: uuid.UUID, db: AsyncSession) -> Campaign:
    """Fetch a campaign by ID or raise 404.

    Raises:
        HTTPException: 404 if the campaign does not exist.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


async def get_live_campaign_or_404(campaign_id: uuid.UUID, db: AsyncSession) -> Campaign:
    """Fetch a campaign by ID, or raise 404 unless it is live.

    Public call paths must not distinguish a missing campaign from a paused or
    draft one, so both answer with the same 404.

    Raises:
        HTTPException: 404 if the campaign does not exist or is not live.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign or campaign.status != "live":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active"
        )
    return campaign


async def resolve_rep_or_422(rep_token: str | None, campaign_id: uuid.UUID) -> dict | None:
    """Return the server-stored rep record behind a rep_token.

    Returns None when no token was supplied.

    Raises:
        HTTPException: 422 when the token is unknown, expired, or was issued
            for a different campaign.
    """
    if not rep_token:
        return None

    rep = await resolve_rep_token(rep_token, str(campaign_id))
    if not rep:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid or expired representative selection",
        )
    return rep


async def resolve_target_ids(
    campaign: Campaign,
    db: AsyncSession,
    rep: dict | None = None,
) -> list[str]:
    """Return target UUIDs for the call flow state.

    When rep is given (rep-lookup path), creates a transient Target row from
    the server-stored rep record, marked with external_id="rep_lookup" and
    target_metadata {"transient": True} so the cleanup task can find it, and
    puts it first, ahead of the campaign's configured targets in their
    configured order. Without a rep the configured targets stand alone.
    """
    ct_result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    configured = [str(ct.target_id) for ct in ct_result.scalars().all()]

    if not rep:
        return configured

    target = Target(
        id=uuid.uuid4(),
        name=(rep.get("name") or "Your Representative")[:200],
        title=(rep.get("title") or "Elected Official")[:100],
        phone_number=rep["phone"],
        location=(rep.get("level") or "").capitalize(),
        external_id="rep_lookup",
        target_metadata={"transient": True},
    )
    db.add(target)
    await db.flush()
    return [str(target.id), *configured]
