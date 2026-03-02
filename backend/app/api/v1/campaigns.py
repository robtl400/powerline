import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import DB, AdminUser
from app.api.v1.helpers import get_campaign_or_404
from app.models.audio import AudioRecording
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_phone_number import CampaignPhoneNumber
from app.models.campaign_target import CampaignTarget
from app.models.phone_number import PhoneNumber
from app.models.target import Target
from app.redis_client import get_redis
from app.schemas.campaign import (
    VALID_TRANSITIONS,
    CallCountResponse,
    CampaignChecklist,
    CampaignCreate,
    CampaignDetailResponse,
    CampaignPublicResponse,
    CampaignResponse,
    CampaignUpdate,
    TargetPublicInfo,
)
from app.schemas.target import ReorderRequest, TargetCreate, TargetInCampaign, TargetUpdate

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _campaign_to_response(campaign: Campaign, target_count: int) -> CampaignResponse:
    return CampaignResponse(
        id=campaign.id,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        campaign_type=campaign.campaign_type,
        language=campaign.language,
        target_ordering=campaign.target_ordering,
        call_maximum=campaign.call_maximum,
        rate_limit=campaign.rate_limit,
        allow_call_in=campaign.allow_call_in,
        allow_webrtc=campaign.allow_webrtc,
        allow_phone_callback=campaign.allow_phone_callback,
        lookup_validate=campaign.lookup_validate,
        lookup_require_mobile=campaign.lookup_require_mobile,
        embed_config=campaign.embed_config,
        talking_points=campaign.talking_points,
        created_by_id=campaign.created_by_id,
        target_count=target_count,
    )


def _target_to_response(target: Target, order: int) -> TargetInCampaign:
    return TargetInCampaign(
        id=target.id,
        created_at=target.created_at,
        name=target.name,
        title=target.title,
        phone_number=target.phone_number,
        location=target.location,
        external_id=target.external_id,
        target_metadata=target.target_metadata,
        order=order,
    )


# ---------------------------------------------------------------------------
# Shared DB helpers
# ---------------------------------------------------------------------------


async def _get_target_count(campaign_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(CampaignTarget.target_id)).where(
            CampaignTarget.campaign_id == campaign_id
        )
    )
    return result.scalar_one()


async def _get_target_in_campaign_or_404(
    campaign_id: uuid.UUID, target_id: uuid.UUID, db: AsyncSession
) -> tuple[Target, CampaignTarget]:
    ct_result = await db.execute(
        select(CampaignTarget).where(
            CampaignTarget.campaign_id == campaign_id,
            CampaignTarget.target_id == target_id,
        )
    )
    ct = ct_result.scalar_one_or_none()
    if not ct:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found in campaign")

    t_result = await db.execute(select(Target).where(Target.id == target_id))
    target = t_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    return target, ct


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns(
    _: AdminUser,
    db: DB,
    status: str | None = Query(default=None),
) -> list[CampaignResponse]:
    count_sq = (
        select(
            CampaignTarget.campaign_id,
            func.count(CampaignTarget.target_id).label("cnt"),
        )
        .group_by(CampaignTarget.campaign_id)
        .subquery()
    )

    stmt = select(Campaign, func.coalesce(count_sq.c.cnt, 0).label("target_count")).outerjoin(
        count_sq, Campaign.id == count_sq.c.campaign_id
    )
    if status:
        stmt = stmt.where(Campaign.status == status)
    stmt = stmt.order_by(Campaign.created_at.desc())

    rows = await db.execute(stmt)
    return [
        _campaign_to_response(row.Campaign, row.target_count)
        for row in rows.all()
    ]


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: AdminUser,
    db: DB,
) -> CampaignResponse:
    campaign = Campaign(**body.model_dump(), created_by_id=current_user.id)
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_response(campaign, 0)


@router.get("/{campaign_id}/count", response_model=CallCountResponse)
async def get_campaign_call_count(
    campaign_id: uuid.UUID,
    db: DB,
) -> CallCountResponse:
    """Public call-count stats for a campaign, cached 10 minutes.

    Used by the embed widget to show 'Join X callers.'
    """
    redis = get_redis()
    cache_key = f"campaign_count:{campaign_id}"

    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return CallCountResponse(**data)

    # Verify the campaign exists (any status — organisations may query before going live).
    result = await db.execute(select(Campaign.id).where(Campaign.id == campaign_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    total_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.campaign_id == campaign_id,
            CallSession.status == "completed",
        )
    )
    total = total_result.scalar_one()

    last_24h_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.campaign_id == campaign_id,
            CallSession.status == "completed",
            CallSession.created_at >= cutoff_24h,
        )
    )
    last_24h = last_24h_result.scalar_one()

    last_7d_result = await db.execute(
        select(func.count(CallSession.id)).where(
            CallSession.campaign_id == campaign_id,
            CallSession.status == "completed",
            CallSession.created_at >= cutoff_7d,
        )
    )
    last_7d = last_7d_result.scalar_one()

    payload = {"total": total, "last_24h": last_24h, "last_7d": last_7d}
    await redis.set(cache_key, json.dumps(payload), ex=600)
    return CallCountResponse(**payload)


@router.get("/{campaign_id}/checklist", response_model=CampaignChecklist)
async def get_campaign_checklist(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> CampaignChecklist:
    """Launch-readiness checklist for a campaign. Admin only."""
    campaign = await get_campaign_or_404(campaign_id, db)

    # Targets
    tc_result = await db.execute(
        select(func.count(CampaignTarget.target_id)).where(
            CampaignTarget.campaign_id == campaign_id
        )
    )
    targets_configured = (tc_result.scalar_one() or 0) > 0

    # Active audio recording for this campaign
    audio_result = await db.execute(
        select(AudioRecording.id).where(
            AudioRecording.campaign_id == campaign_id,
            AudioRecording.is_active.is_(True),
        ).limit(1)
    )
    audio_configured = audio_result.scalar_one_or_none() is not None

    # Phone number assigned + STIR/SHAKEN verification
    pn_result = await db.execute(
        select(PhoneNumber.trust_status)
        .join(CampaignPhoneNumber, PhoneNumber.id == CampaignPhoneNumber.phone_number_id)
        .where(CampaignPhoneNumber.campaign_id == campaign_id)
        .limit(1)
    )
    row = pn_result.one_or_none()
    phone_number_assigned = row is not None
    phone_verified = phone_number_assigned and row[0] == "twilio-approved"

    talking_points_written = bool(campaign.talking_points and campaign.talking_points.strip())

    return CampaignChecklist(
        targets_configured=targets_configured,
        audio_configured=audio_configured,
        phone_number_assigned=phone_number_assigned,
        phone_verified=phone_verified,
        talking_points_written=talking_points_written,
    )


@router.get("/{campaign_id}/public", response_model=CampaignPublicResponse)
async def get_campaign_public(
    campaign_id: uuid.UUID,
    db: DB,
    response: Response,
) -> CampaignPublicResponse:
    """Public campaign info for the embed widget.

    Returns campaign metadata and target display info (no phone numbers).
    Only live campaigns are accessible.
    """
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()

    if not campaign or campaign.status != "live":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active")

    ct_result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    campaign_targets = ct_result.scalars().all()

    target_infos: list[TargetPublicInfo] = []
    if campaign_targets:
        target_ids = [ct.target_id for ct in campaign_targets]
        t_result = await db.execute(select(Target).where(Target.id.in_(target_ids)))
        targets_by_id = {t.id: t for t in t_result.scalars().all()}
        target_infos = [
            TargetPublicInfo(
                id=ct.target_id,
                name=targets_by_id[ct.target_id].name,
                title=targets_by_id[ct.target_id].title,
                location=targets_by_id[ct.target_id].location,
            )
            for ct in campaign_targets
            if ct.target_id in targets_by_id
        ]

    response.headers["Cache-Control"] = "public, max-age=60"
    return CampaignPublicResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        talking_points=campaign.talking_points,
        allow_webrtc=campaign.allow_webrtc,
        allow_phone_callback=campaign.allow_phone_callback,
        targets=target_infos,
    )


@router.get("/{campaign_id}", response_model=CampaignDetailResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> CampaignDetailResponse:
    result = await db.execute(
        select(Campaign)
        .where(Campaign.id == campaign_id)
        .options(selectinload(Campaign.campaign_targets))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    targets_in_campaign: list[TargetInCampaign] = []
    if campaign.campaign_targets:
        target_ids = [ct.target_id for ct in campaign.campaign_targets]
        t_result = await db.execute(select(Target).where(Target.id.in_(target_ids)))
        targets_by_id = {t.id: t for t in t_result.scalars().all()}

        targets_in_campaign = [
            _target_to_response(targets_by_id[ct.target_id], ct.order)
            for ct in campaign.campaign_targets
            if ct.target_id in targets_by_id
        ]

    base = _campaign_to_response(campaign, len(targets_in_campaign))
    return CampaignDetailResponse(**base.model_dump(), targets=targets_in_campaign)


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    _: AdminUser,
    db: DB,
) -> CampaignResponse:
    campaign = await get_campaign_or_404(campaign_id, db)
    updates = body.model_dump(exclude_unset=True)

    if "status" in updates:
        new_status = updates["status"]
        allowed = VALID_TRANSITIONS.get(campaign.status, [])
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot transition from '{campaign.status}' to '{new_status}'. Allowed: {allowed}",
            )

    for field, value in updates.items():
        setattr(campaign, field, value)

    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)

    count = await _get_target_count(campaign_id, db)
    return _campaign_to_response(campaign, count)


@router.post("/{campaign_id}/archive", response_model=CampaignResponse)
async def archive_campaign(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> CampaignResponse:
    campaign = await get_campaign_or_404(campaign_id, db)

    allowed = VALID_TRANSITIONS.get(campaign.status, [])
    if "archived" not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Cannot archive a campaign with status '{campaign.status}'",
        )

    campaign.status = "archived"
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(campaign)

    count = await _get_target_count(campaign_id, db)
    return _campaign_to_response(campaign, count)


# ---------------------------------------------------------------------------
# Target management
# Note: /reorder is registered BEFORE /{target_id} to avoid routing conflicts.
# ---------------------------------------------------------------------------


@router.patch("/{campaign_id}/targets/reorder", response_model=list[TargetInCampaign])
async def reorder_targets(
    campaign_id: uuid.UUID,
    body: ReorderRequest,
    _: AdminUser,
    db: DB,
) -> list[TargetInCampaign]:
    campaign = await get_campaign_or_404(campaign_id, db)

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    existing_cts = {ct.target_id: ct for ct in ct_result.scalars().all()}

    if set(body.target_ids) != set(existing_cts.keys()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target_ids must contain exactly the current targets for this campaign",
        )

    for new_order, target_id in enumerate(body.target_ids):
        existing_cts[target_id].order = new_order

    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()

    t_result = await db.execute(
        select(Target).where(Target.id.in_(list(existing_cts.keys())))
    )
    targets_by_id = {t.id: t for t in t_result.scalars().all()}

    return [
        _target_to_response(targets_by_id[tid], i)
        for i, tid in enumerate(body.target_ids)
        if tid in targets_by_id
    ]


@router.post("/{campaign_id}/targets", response_model=TargetInCampaign, status_code=status.HTTP_201_CREATED)
async def add_target(
    campaign_id: uuid.UUID,
    body: TargetCreate,
    _: AdminUser,
    db: DB,
) -> TargetInCampaign:
    campaign = await get_campaign_or_404(campaign_id, db)

    max_result = await db.execute(
        select(func.coalesce(func.max(CampaignTarget.order), -1)).where(
            CampaignTarget.campaign_id == campaign.id
        )
    )
    next_order = max_result.scalar_one() + 1

    target = Target(
        name=body.name,
        title=body.title,
        phone_number=body.phone_number,
        location=body.location,
        external_id=body.external_id,
        target_metadata=body.target_metadata,
    )
    db.add(target)
    await db.flush()

    ct = CampaignTarget(campaign_id=campaign.id, target_id=target.id, order=next_order)
    db.add(ct)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target)

    return _target_to_response(target, next_order)


@router.patch("/{campaign_id}/targets/{target_id}", response_model=TargetInCampaign)
async def update_target(
    campaign_id: uuid.UUID,
    target_id: uuid.UUID,
    body: TargetUpdate,
    _: AdminUser,
    db: DB,
) -> TargetInCampaign:
    target, ct = await _get_target_in_campaign_or_404(campaign_id, target_id, db)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(target, field, value)

    campaign = await get_campaign_or_404(campaign_id, db)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(target)

    return _target_to_response(target, ct.order)


@router.delete("/{campaign_id}/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_target(
    campaign_id: uuid.UUID,
    target_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> None:
    target, ct = await _get_target_in_campaign_or_404(campaign_id, target_id, db)

    await db.delete(ct)
    await db.delete(target)

    campaign = await get_campaign_or_404(campaign_id, db)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
