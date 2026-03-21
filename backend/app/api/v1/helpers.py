"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target


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


async def resolve_target_ids(
    campaign: Campaign,
    db: AsyncSession,
    target_phone_override: str | None = None,
    target_rep_name: str | None = None,
    target_rep_title: str | None = None,
) -> list[str]:
    """Return target UUIDs for the call flow state.

    When target_phone_override is set (rep-lookup path), creates a transient
    Target row marked with external_id="rep_lookup" and returns its UUID.
    Otherwise loads the campaign's configured targets from the DB.
    """
    if target_phone_override:
        target = Target(
            id=uuid.uuid4(),
            name=target_rep_name or "Your Representative",
            title=target_rep_title or "Elected Official",
            phone_number=target_phone_override,
            location="",
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
