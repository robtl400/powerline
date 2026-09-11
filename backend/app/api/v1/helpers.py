"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import hashlib
import hmac
import random
import uuid
from typing import NamedTuple
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
from app.schemas.calls import TargetPreview
from app.schemas.target import MAX_LENGTHS
from app.services.call_state import save_call_state
from app.services.civic_service import normalize_rep_phone, resolve_rep_token

log = structlog.get_logger()

UPLOAD_CHUNK_BYTES = 64 * 1024

INVALID_REP_SELECTION = "Invalid or expired representative selection"
REP_TOKEN_INVALID_CODE = "rep_token_invalid"

# CallSession statuses that count as a call. A session reaches one of these only
# after Twilio connects it, so an `initiated` row — opened by a public call or
# token request that may never connect — is not a call. `failed` is excluded
# because the status column cannot separate a call that connected and then
# dropped from one that never left the API.
CONNECTED_CALL_STATUSES = ("in_progress", "completed")


def phone_hash(e164: str) -> str:
    """Return the stored digest of a canonical E.164 number.

    With PHONE_HASH_PEPPER set the digest is an HMAC-SHA256 under that secret,
    so a stolen blocklist or session table cannot be walked back to phone
    numbers by hashing the ten-digit space. With the pepper empty it is a plain
    SHA-256 digest.
    """
    pepper = settings.PHONE_HASH_PEPPER
    if pepper:
        return hmac.new(pepper.encode(), e164.encode(), hashlib.sha256).hexdigest()
    return hashlib.sha256(e164.encode()).hexdigest()


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
            detail={"message": INVALID_REP_SELECTION, "code": REP_TOKEN_INVALID_CODE},
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
    configured order. A configured target that carries the same number as the
    rep is dropped, so one office is never dialed twice in a session. Without a
    rep the configured targets stand alone.

    Raises:
        HTTPException: 422 when the stored rep record holds a number that is
            not a dialable US line — indistinguishable, to the caller, from a
            handle that never resolved.
    """
    ct_result = await db.execute(
        select(CampaignTarget.target_id, Target.phone_number)
        .join(Target, Target.id == CampaignTarget.target_id)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    configured_rows = ct_result.all()

    if not rep:
        return [str(row.target_id) for row in configured_rows]

    phone = normalize_rep_phone(rep.get("phone"))
    if not phone:
        log.warning("rep_target_phone_undialable", campaign_id=str(campaign.id))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": INVALID_REP_SELECTION, "code": REP_TOKEN_INVALID_CODE},
        )

    configured = [
        str(row.target_id)
        for row in configured_rows
        if (normalize_rep_phone(row.phone_number) or row.phone_number) != phone
    ]
    if len(configured) != len(configured_rows):
        log.info("rep_target_deduplicated", campaign_id=str(campaign.id))

    target = Target(
        id=uuid.uuid4(),
        name=(rep.get("name") or "Your Representative")[: MAX_LENGTHS["name"]],
        title=(rep.get("title") or "Elected Official")[: MAX_LENGTHS["title"]],
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

    The ceiling bounds connected calls: only sessions in
    CONNECTED_CALL_STATUSES count against it, so opening a session costs
    nothing until Twilio connects it. Sessions already sitting at `initiated`
    are therefore admitted work — N of them may still connect after the ceiling
    is reached, and the campaign settles at up to call_maximum + N calls.

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
        select(func.count())
        .select_from(CallSession)
        .where(
            CallSession.campaign_id == campaign.id,
            CallSession.status.in_(CONNECTED_CALL_STATUSES),
        )
    )
    if (count_result.scalar_one() or 0) >= campaign.call_maximum:
        log.warning("campaign_call_maximum_reached", campaign_id=str(campaign.id))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This campaign has reached its call limit",
        )


class StartedCall(NamedTuple):
    """The open session and the target its first dial will reach."""

    session_id: uuid.UUID
    first_target: TargetPreview | None


async def start_call_session(
    campaign: Campaign,
    db: AsyncSession,
    *,
    connection_type: str,
    rep_token: str | None,
    client_ip: str,
    caller_phone_hash: str | None = None,
    referral_code: str | None = None,
) -> StartedCall:
    """Resolve the call's targets, claim a ceiling slot, and open a CallSession.

    Shared by both public call paths: it settles the target list, reserves the
    session against the campaign's ceiling and inserts it in one transaction,
    then writes the Redis state the webhook chain reads.

    Returns the session id alongside the name and title of the first target in
    the settled order, so the widget names the official it is about to dial
    even when the campaign shuffles.

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

    first_row = (
        await db.execute(
            select(Target.name, Target.title).where(Target.id == uuid.UUID(target_ids[0]))
        )
    ).first()
    first_target = (
        TargetPreview(name=first_row.name, title=first_row.title) if first_row else None
    )

    await reserve_call_slot(campaign, db)

    session_id = uuid.uuid4()
    db.add(
        CallSession(
            id=session_id,
            campaign_id=campaign.id,
            connection_type=connection_type,
            caller_phone_hash=caller_phone_hash,
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

    return StartedCall(session_id=session_id, first_target=first_target)
