"""Admin-only utility endpoints.

Exposes blocklist CRUD and global dashboard analytics.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser
from app.models.blocklist import BlocklistEntry
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.schemas.admin import BlocklistCreate, BlocklistResponse
from app.schemas.analytics import DailyCount, DashboardResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def _to_response(e: BlocklistEntry) -> BlocklistResponse:
    return BlocklistResponse.model_validate(e)


# ---------------------------------------------------------------------------
# GET /admin/dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    _: AdminUser,
    db: DB,
) -> DashboardResponse:
    """Return global call activity summary for the admin dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    calls_today: int = await db.scalar(
        select(func.count()).select_from(CallSession)
        .where(CallSession.created_at >= today_start)
    ) or 0

    calls_this_week: int = await db.scalar(
        select(func.count()).select_from(CallSession)
        .where(CallSession.created_at >= week_start)
    ) or 0

    calls_this_month: int = await db.scalar(
        select(func.count()).select_from(CallSession)
        .where(CallSession.created_at >= month_start)
    ) or 0

    active_campaigns: int = await db.scalar(
        select(func.count()).select_from(Campaign)
        .where(Campaign.status == "live")
    ) or 0

    # WebRTC vs phone breakdown (all time)
    ct_result = await db.execute(
        select(CallSession.connection_type, func.count().label("cnt"))
        .group_by(CallSession.connection_type)
    )
    ct_map: dict[str, int] = {row.connection_type: row.cnt for row in ct_result.all()}
    webrtc_count = ct_map.get("webrtc", 0)
    phone_count = ct_map.get("outbound_phone", 0) + ct_map.get("inbound_phone", 0)

    # Daily call volumes for the last 7 calendar days
    seven_days_ago = today_start - timedelta(days=6)  # 7 days inclusive of today
    date_trunc = func.date_trunc("day", CallSession.created_at)
    daily_result = await db.execute(
        select(date_trunc.label("day"), func.count().label("count"))
        .where(CallSession.created_at >= seven_days_ago)
        .group_by(date_trunc)
        .order_by(date_trunc)
    )
    daily_rows = {row.day.date(): row.count for row in daily_result.all()}

    # Fill in zeros for days with no calls so the chart has a complete series
    calls_last_7_days: list[DailyCount] = []
    for i in range(6, -1, -1):
        day = (today_start - timedelta(days=i)).date()
        calls_last_7_days.append(DailyCount(date=day.isoformat(), count=daily_rows.get(day, 0)))

    return DashboardResponse(
        calls_today=calls_today,
        calls_this_week=calls_this_week,
        calls_this_month=calls_this_month,
        active_campaigns=active_campaigns,
        webrtc_count=webrtc_count,
        phone_count=phone_count,
        calls_last_7_days=calls_last_7_days,
    )


# ---------------------------------------------------------------------------
# GET /admin/blocklist
# ---------------------------------------------------------------------------

@router.get("/blocklist", response_model=list[BlocklistResponse])
async def list_blocklist(
    _: AdminUser,
    db: DB,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, le=500),
) -> list[BlocklistResponse]:
    """Return blocklist entries ordered by creation date descending."""
    result = await db.execute(
        select(BlocklistEntry)
        .order_by(BlocklistEntry.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return [_to_response(e) for e in result.scalars().all()]


# ---------------------------------------------------------------------------
# POST /admin/blocklist
# ---------------------------------------------------------------------------

@router.post("/blocklist", response_model=BlocklistResponse, status_code=status.HTTP_201_CREATED)
async def create_blocklist_entry(
    body: BlocklistCreate,
    current_user: AdminUser,
    db: DB,
) -> BlocklistResponse:
    """Add a phone hash and/or IP address to the blocklist."""
    entry = BlocklistEntry(
        phone_hash=body.phone_hash,
        ip_address=body.ip_address,
        reason=body.reason,
        created_by_id=current_user.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _to_response(entry)


# ---------------------------------------------------------------------------
# DELETE /admin/blocklist/{entry_id}
# ---------------------------------------------------------------------------

@router.delete("/blocklist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blocklist_entry(
    entry_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> None:
    """Remove a blocklist entry."""
    result = await db.execute(
        select(BlocklistEntry).where(BlocklistEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    await db.delete(entry)
    await db.commit()
