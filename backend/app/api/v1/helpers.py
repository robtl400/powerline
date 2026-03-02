"""Shared route helpers used by multiple routers."""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign


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
