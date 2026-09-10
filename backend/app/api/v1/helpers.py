"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.services.civic_service import resolve_rep_token


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
    the server-stored rep record, marked with external_id="rep_lookup", and
    returns its UUID. Otherwise loads the campaign's configured targets.
    """
    if rep:
        target = Target(
            id=uuid.uuid4(),
            name=(rep.get("name") or "Your Representative")[:200],
            title=(rep.get("title") or "Elected Official")[:100],
            phone_number=rep["phone"],
            location=(rep.get("level") or "").capitalize(),
            external_id="rep_lookup",
        )
        db.add(target)
        await db.flush()
        return [str(target.id)]

    ct_result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    return [str(ct.target_id) for ct in ct_result.scalars().all()]
