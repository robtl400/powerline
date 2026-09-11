"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import random
import uuid
from zoneinfo import ZoneInfo

import structlog
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.call_state import save_call_state
from app.services.civic_service import normalize_rep_phone, resolve_rep_token

log = structlog.get_logger()

UPLOAD_CHUNK_BYTES = 64 * 1024

INVALID_REP_SELECTION = "Invalid or expired representative selection"


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
            detail=INVALID_REP_SELECTION,
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

    Raises:
        HTTPException: 422 when the stored rep record holds a number that is
            not a dialable US line — indistinguishable, to the caller, from a
            handle that never resolved.
    """
    ct_result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    configured = [str(ct.target_id) for ct in ct_result.scalars().all()]

    if not rep:
        return configured

    phone = normalize_rep_phone(rep.get("phone"))
    if not phone:
        log.warning("rep_target_phone_undialable", campaign_id=str(campaign.id))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=INVALID_REP_SELECTION,
        )

    target = Target(
        id=uuid.uuid4(),
        name=(rep.get("name") or "Your Representative")[:200],
        title=(rep.get("title") or "Elected Official")[:100],
        phone_number=phone,
        location=(rep.get("level") or "").capitalize(),
        external_id="rep_lookup",
        target_metadata={"transient": True},
    )
    db.add(target)
    await db.flush()
    return [str(target.id), *configured]


async def reserve_call_slot(campaign: Campaign, db: AsyncSession) -> None:
    """Claim one slot under the campaign's lifetime call ceiling.

    Takes a transaction-scoped advisory lock on the campaign before counting,
    so concurrent requests queue behind one another and each one's count
    already includes every session committed ahead of it. Postgres releases the
    lock at commit — the same commit that writes the CallSession — so the count
    a caller admits itself on cannot go stale between the check and the insert.

    Raises:
        HTTPException: 429 once the campaign has reached its call limit.
    """
    if campaign.call_maximum is None:
        return

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(CAST(:campaign_key AS text)))"),
        {"campaign_key": str(campaign.id)},
    )

    count_result = await db.execute(
        select(func.count()).select_from(CallSession).where(CallSession.campaign_id == campaign.id)
    )
    if (count_result.scalar_one() or 0) >= campaign.call_maximum:
        log.warning("campaign_call_maximum_reached", campaign_id=str(campaign.id))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This campaign has reached its call limit",
        )


async def start_call_session(
    campaign: Campaign,
    db: AsyncSession,
    *,
    connection_type: str,
    rep_token: str | None,
    client_ip: str,
    caller_phone_hash: str | None = None,
    from_number: str | None = None,
    referral_code: str | None = None,
) -> uuid.UUID:
    """Resolve the call's targets, claim a ceiling slot, and open a CallSession.

    Shared by both public call paths: it settles the target list, reserves the
    session against the campaign's ceiling and inserts it in one transaction,
    then writes the Redis state the webhook chain reads.

    Both network hops belong to the caller, not to this helper: place the
    Twilio call after it returns, so the ceiling lock is never held across an
    outbound request.

    Raises:
        HTTPException: 422 when the rep handle or the target list is unusable,
            429 when the campaign has reached its call limit.
    """
    rep = await resolve_rep_or_422(rep_token, campaign.id)
    target_ids = await resolve_target_ids(campaign, db, rep=rep)

    if not target_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Campaign has no targets configured",
        )

    if campaign.target_ordering == "shuffle" and rep is None:
        random.shuffle(target_ids)

    await reserve_call_slot(campaign, db)

    session_id = uuid.uuid4()
    db.add(
        CallSession(
            id=session_id,
            campaign_id=campaign.id,
            connection_type=connection_type,
            caller_phone_hash=caller_phone_hash,
            from_number=from_number,
            referral_code=referral_code,
            status="initiated",
        )
    )
    await db.commit()

    log.info(
        "call_session_created",
        session_id=str(session_id),
        campaign_id=str(campaign.id),
        connection_type=connection_type,
        target_count=len(target_ids),
    )

    await save_call_state(
        session_id,
        {
            "campaign_id": str(campaign.id),
            "target_ids": target_ids,
            "current_target_index": 0,
            "caller_phone_hash": caller_phone_hash or "",
            "connection_type": connection_type,
            "client_ip": client_ip,
        },
    )

    return session_id
