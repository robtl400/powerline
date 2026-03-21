import csv
import io
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status
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
from app.schemas.target import ImportResult, ImportRowError, ReorderRequest, TargetCreate, TargetInCampaign, TargetUpdate
from app.schemas.target import normalize_phone

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

    embed_config: dict = campaign.embed_config or {}
    response.headers["Cache-Control"] = "public, max-age=60"
    return CampaignPublicResponse(
        id=campaign.id,
        name=campaign.name,
        description=campaign.description,
        talking_points=campaign.talking_points,
        allow_webrtc=campaign.allow_webrtc,
        allow_phone_callback=campaign.allow_phone_callback,
        targets=target_infos,
        target_levels=embed_config.get("target_levels", []),
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


# Keep in sync with _FIELD_ALIASES in frontend/src/hooks/useCampaignData.ts
_KNOWN_FIELDS = {"name", "title", "phone_number", "location", "external_id"}
_REQUIRED_FIELDS = {"name", "title", "phone_number", "location"}
_MAX_CSV_BYTES = 5 * 1024 * 1024  # 5 MB


async def _do_import(
    campaign_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession,
    redis: object,
) -> ImportResult:
    """Core import logic — called inside the per-campaign Redis lock."""
    content = await file.read()

    if len(content) > _MAX_CSV_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 5 MB limit")

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not filename.endswith(".csv") and "csv" not in content_type and "text/plain" not in content_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV has no data rows")

    headers = {h.lower().strip() for h in (reader.fieldnames or [])}
    missing = _REQUIRED_FIELDS - headers
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV missing required columns: {', '.join(sorted(missing))}",
        )

    campaign = await get_campaign_or_404(campaign_id, db)

    # Load existing targets in this campaign keyed by external_id for upsert lookup
    existing_result = await db.execute(
        select(Target, CampaignTarget)
        .join(CampaignTarget, CampaignTarget.target_id == Target.id)
        .where(
            CampaignTarget.campaign_id == campaign_id,
            Target.external_id.isnot(None),
        )
    )
    existing_by_ext_id: dict[str, Target] = {
        row.Target.external_id: row.Target for row in existing_result.all()
    }

    # Current max order for appending new targets
    max_order_result = await db.execute(
        select(func.coalesce(func.max(CampaignTarget.order), -1)).where(
            CampaignTarget.campaign_id == campaign_id
        )
    )
    next_order = max_order_result.scalar_one() + 1

    errors: list[ImportRowError] = []
    new_targets: list[Target] = []
    updated_count = 0

    for idx, raw_row in enumerate(rows):
        row_num = idx + 2  # 1-based, +1 for header
        row = {k.lower().strip(): (v or "").strip() for k, v in raw_row.items()}

        # Validate required fields
        missing_vals = [f for f in _REQUIRED_FIELDS if not row.get(f)]
        if missing_vals:
            errors.append(ImportRowError(
                row=row_num,
                error=f"missing required field: {', '.join(sorted(missing_vals))}",
            ))
            continue

        # Validate phone number
        try:
            phone = normalize_phone(row["phone_number"])
        except ValueError as exc:
            errors.append(ImportRowError(row=row_num, error=f"invalid phone number: {row['phone_number']} — {exc}"))
            continue

        external_id = row.get("external_id") or None
        extra_cols = {k: v for k, v in row.items() if k not in _KNOWN_FIELDS and v}
        target_metadata = extra_cols if extra_cols else {}

        # Upsert: update existing if external_id matches
        if external_id and external_id in existing_by_ext_id:
            existing = existing_by_ext_id[external_id]
            existing.name = row["name"]
            existing.title = row["title"]
            existing.phone_number = phone
            existing.location = row["location"]
            existing.target_metadata = target_metadata
            updated_count += 1
        else:
            new_targets.append(Target(
                name=row["name"],
                title=row["title"],
                phone_number=phone,
                location=row["location"],
                external_id=external_id,
                target_metadata=target_metadata,
            ))

    # Bulk insert new targets
    if new_targets:
        db.add_all(new_targets)
        await db.flush()

        new_cts = [
            CampaignTarget(campaign_id=campaign.id, target_id=t.id, order=next_order + i)
            for i, t in enumerate(new_targets)
        ]
        db.add_all(new_cts)

    if new_targets or updated_count:
        campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()

    # Cache errors in Redis (TTL 1 hour) for the download endpoint.
    # Non-fatal: DB commit already succeeded. If Redis is unavailable, log and
    # continue — the ImportResult.errors field already contains the error list.
    try:
        await redis.set(  # type: ignore[union-attr]
            f"import_errors:{campaign_id}",
            json.dumps([{"row": e.row, "error": e.error} for e in errors]),
            ex=3600,
        )
    except Exception:
        logger.warning(
            "import_errors Redis cache write failed for campaign %s; errors returned in response body only",
            campaign_id,
        )

    return ImportResult(imported=len(new_targets), updated=updated_count, errors=errors)


@router.post("/{campaign_id}/targets/import", response_model=ImportResult)
async def import_targets(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
    file: UploadFile = File(...),
) -> ImportResult:
    """Bulk-import targets from a CSV file. Partial success: valid rows commit even if some fail."""
    # Acquire per-campaign import lock to prevent concurrent imports from creating
    # duplicate targets when the same external_id appears in overlapping requests.
    redis = get_redis()
    lock_key = f"import_lock:{campaign_id}"
    locked = await redis.set(lock_key, "1", nx=True, ex=60)
    if not locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An import is already in progress for this campaign. Please wait and try again.",
        )

    try:
        return await _do_import(campaign_id, file, db, redis)
    finally:
        await redis.delete(lock_key)


@router.get("/{campaign_id}/targets/import-errors")
async def download_import_errors(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> Response:
    """Download the last import's error rows as a CSV file."""
    await get_campaign_or_404(campaign_id, db)

    redis = get_redis()
    data = await redis.get(f"import_errors:{campaign_id}")
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recent import errors found")

    errors = json.loads(data)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["row", "error_reason"])
    for e in errors:
        writer.writerow([e["row"], e["error"]])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=import-errors-{campaign_id}.csv"},
    )


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
