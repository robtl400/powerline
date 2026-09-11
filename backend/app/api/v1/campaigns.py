import asyncio
import csv
import io
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, CurrentUser
from app.api.v1.helpers import (
    CONNECTED_CALL_STATUSES,
    get_campaign_or_404,
    get_live_campaign_or_404,
    read_upload_limited,
)
from app.config import settings
from app.dependencies import get_client_ip
from app.models.audio import AudioRecording
from app.models.call import Call
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
    CampaignPage,
    CampaignPublicResponse,
    CampaignResponse,
    CampaignStatus,
    CampaignUpdate,
    TargetPublicInfo,
)
from app.schemas.target import ImportResult, ImportRowError, ReorderRequest, TargetCreate, TargetInCampaign, TargetUpdate
from app.schemas.target import MAX_LENGTHS, to_us_e164
from app.services.rate_limiter import check_rate_limit
from app.tasks.lock import RELEASE_IF_OWNER

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _campaign_to_response(
    campaign: Campaign,
    target_count: int,
    session_count: int,
    completed_session_count: int,
) -> CampaignResponse:
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
        allow_webrtc=campaign.allow_webrtc,
        allow_phone_callback=campaign.allow_phone_callback,
        lookup_validate=campaign.lookup_validate,
        lookup_require_mobile=campaign.lookup_require_mobile,
        embed_config=campaign.embed_config,
        talking_points=campaign.talking_points,
        created_by_id=campaign.created_by_id,
        target_count=target_count,
        session_count=session_count,
        completed_session_count=completed_session_count,
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


# Partial unique index: campaign names must be unique among non-archived campaigns.
_NAME_INDEX = "ux_campaigns_name_active"


async def _commit_unique_name(db: AsyncSession) -> None:
    """Commit, turning a campaign-name collision into 409 instead of a 500."""
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if _NAME_INDEX not in str(exc):
            raise
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A campaign with that name already exists",
        )


async def _get_target_count(campaign_id: uuid.UUID, db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(CampaignTarget.target_id)).where(
            CampaignTarget.campaign_id == campaign_id
        )
    )
    return result.scalar_one()


class _SessionCounts(NamedTuple):
    """Connected call sessions a campaign has, and how many reached `completed`."""

    total: int
    completed: int


_COMPLETED_SESSIONS = func.count(case((CallSession.status == "completed", 1)))


async def _get_session_counts(campaign_id: uuid.UUID, db: AsyncSession) -> _SessionCounts:
    """Count the campaign's sessions that Twilio connected.

    Sessions still at `initiated` are excluded: the public call and token
    endpoints open one per request, and one that never connects is not a call.
    """
    row = (
        await db.execute(
            select(
                func.count(CallSession.id).label("total"),
                _COMPLETED_SESSIONS.label("completed"),
            ).where(
                CallSession.campaign_id == campaign_id,
                CallSession.status.in_(CONNECTED_CALL_STATUSES),
            )
        )
    ).one()
    return _SessionCounts(total=row.total, completed=row.completed)


async def _next_order(campaign_id: uuid.UUID, db: AsyncSession) -> int:
    """The order value that appends a target to the end of a campaign's list."""
    result = await db.execute(
        select(func.coalesce(func.max(CampaignTarget.order), -1)).where(
            CampaignTarget.campaign_id == campaign_id
        )
    )
    return result.scalar_one() + 1


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


@router.get("", response_model=CampaignPage)
async def list_campaigns(
    _: CurrentUser,
    db: DB,
    status: CampaignStatus | None = Query(default=None),
    q: str | None = Query(default=None, max_length=100),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, le=500),
) -> CampaignPage:
    """One page of campaigns, with `total` counting every campaign the filters match.

    The page is fetched first and its per-campaign target and session counts are
    aggregated in one grouped query each, restricted to the campaigns on the
    page, so neither aggregate scans rows belonging to campaigns not returned.
    """
    filters = []
    if status:
        filters.append(Campaign.status == status)
    if q and q.strip():
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters.append(Campaign.name.ilike(f"%{term}%", escape="\\"))

    total = await db.scalar(
        select(func.count()).select_from(Campaign).where(*filters)
    )

    page = (
        (
            await db.execute(
                select(Campaign)
                .where(*filters)
                .order_by(Campaign.created_at.desc())
                .offset(skip)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    if not page:
        return CampaignPage(total=total or 0, items=[])

    page_ids = [campaign.id for campaign in page]

    target_rows = await db.execute(
        select(
            CampaignTarget.campaign_id,
            func.count(CampaignTarget.target_id).label("cnt"),
        )
        .where(CampaignTarget.campaign_id.in_(page_ids))
        .group_by(CampaignTarget.campaign_id)
    )
    target_counts = {row.campaign_id: row.cnt for row in target_rows}

    session_rows = await db.execute(
        select(
            CallSession.campaign_id,
            func.count(CallSession.id).label("sessions"),
            _COMPLETED_SESSIONS.label("completed"),
        )
        .where(
            CallSession.campaign_id.in_(page_ids),
            CallSession.status.in_(CONNECTED_CALL_STATUSES),
        )
        .group_by(CallSession.campaign_id)
    )
    session_counts = {row.campaign_id: (row.sessions, row.completed) for row in session_rows}

    items = []
    for campaign in page:
        sessions, completed = session_counts.get(campaign.id, (0, 0))
        items.append(
            _campaign_to_response(
                campaign,
                target_counts.get(campaign.id, 0),
                sessions,
                completed,
            )
        )
    return CampaignPage(total=total or 0, items=items)


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    current_user: AdminUser,
    db: DB,
) -> CampaignResponse:
    campaign = Campaign(**body.model_dump(), created_by_id=current_user.id)
    db.add(campaign)
    await _commit_unique_name(db)
    await db.refresh(campaign)
    return _campaign_to_response(campaign, 0, 0, 0)


@router.get("/{campaign_id}/count", response_model=CallCountResponse)
async def get_campaign_call_count(
    campaign_id: uuid.UUID,
    request: Request,
    db: DB,
) -> CallCountResponse:
    """Public call-count stats for a live campaign, cached 10 minutes.

    Used by the embed widget to show 'Join X callers.' Rate limited per client
    IP, and only live campaigns resolve — a draft or paused campaign answers the
    same 404 as a missing one.
    """
    redis = get_redis()
    await check_rate_limit(redis, "count", get_client_ip(request), settings.PUBLIC_RATE_LIMIT)

    await get_live_campaign_or_404(campaign_id, db)

    cache_key = f"campaign_count:{campaign_id}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        return CallCountResponse(**data)

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)
    cutoff_7d = now - timedelta(days=7)

    counts = (
        await db.execute(
            select(
                func.count(CallSession.id).label("total"),
                func.count(case((CallSession.created_at >= cutoff_24h, 1))).label("last_24h"),
                func.count(case((CallSession.created_at >= cutoff_7d, 1))).label("last_7d"),
            ).where(
                CallSession.campaign_id == campaign_id,
                CallSession.status == "completed",
            )
        )
    ).one()

    payload = {"total": counts.total, "last_24h": counts.last_24h, "last_7d": counts.last_7d}
    await redis.set(cache_key, json.dumps(payload), ex=_COUNT_CACHE_TTL_SECONDS)
    return CallCountResponse(**payload)


@router.get("/{campaign_id}/checklist", response_model=CampaignChecklist)
async def get_campaign_checklist(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
) -> CampaignChecklist:
    """Launch-readiness checklist for a campaign."""
    campaign = await get_campaign_or_404(campaign_id, db)

    targets_configured = await _get_target_count(campaign_id, db) > 0

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
    request: Request,
    db: DB,
    response: Response,
) -> CampaignPublicResponse:
    """Public campaign info for the embed widget.

    Returns campaign metadata and target display info (no phone numbers).
    Only live campaigns are accessible, and callers are rate limited per IP.
    """
    await check_rate_limit(get_redis(), "public", get_client_ip(request), settings.PUBLIC_RATE_LIMIT)

    campaign = await get_live_campaign_or_404(campaign_id, db)

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
    _: CurrentUser,
    db: DB,
    include_targets: bool = Query(default=True),
    targets_limit: int = Query(default=500, ge=1, le=2000),
) -> CampaignDetailResponse:
    """Campaign detail. `targets` holds at most `targets_limit` rows in campaign order;
    `targets_total` reports how many the campaign has."""
    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    targets_total = await _get_target_count(campaign_id, db)

    targets_in_campaign: list[TargetInCampaign] = []
    if include_targets and targets_total:
        rows = await db.execute(
            select(Target, CampaignTarget.order)
            .join(CampaignTarget, CampaignTarget.target_id == Target.id)
            .where(CampaignTarget.campaign_id == campaign_id)
            .order_by(CampaignTarget.order)
            .limit(targets_limit)
        )
        targets_in_campaign = [_target_to_response(target, order) for target, order in rows.all()]

    sessions = await _get_session_counts(campaign_id, db)

    base = _campaign_to_response(campaign, targets_total, sessions.total, sessions.completed)
    return CampaignDetailResponse(
        **base.model_dump(),
        targets=targets_in_campaign,
        targets_total=targets_total,
    )


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
        new_status = updates.pop("status")
        current_status = campaign.status
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot transition from '{current_status}' to '{new_status}'. Allowed: {allowed}",
            )

        # Guard the transition against the status the check was made on, so a
        # concurrent change cannot be overwritten by this stale decision.
        transition = await db.execute(
            update(Campaign)
            .where(Campaign.id == campaign_id, Campaign.status == current_status)
            .values(status=new_status, updated_at=datetime.now(timezone.utc))
        )
        if transition.rowcount == 0:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Campaign status changed, reload and try again",
            )

    for field, value in updates.items():
        setattr(campaign, field, value)

    campaign.updated_at = datetime.now(timezone.utc)
    await _commit_unique_name(db)
    await db.refresh(campaign)

    count = await _get_target_count(campaign_id, db)
    sessions = await _get_session_counts(campaign_id, db)
    return _campaign_to_response(campaign, count, sessions.total, sessions.completed)


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
    sessions = await _get_session_counts(campaign_id, db)
    return _campaign_to_response(campaign, count, sessions.total, sessions.completed)


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
_COUNT_CACHE_TTL_SECONDS = 600
_IMPORT_LOCK_TTL_SECONDS = 300
_IMPORT_ERRORS_TTL_SECONDS = 3600

# A cell starting with one of these is read as a formula by spreadsheet software,
# so exported values are prefixed with a quote to keep them inert text.
_FORMULA_LEAD_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(value: object) -> str:
    text = str(value)
    if text[:1] in _FORMULA_LEAD_CHARS:
        return f"'{text}"
    return text


class _ImportRow(NamedTuple):
    """One CSV row that passed validation, ready to insert or upsert."""

    name: str
    title: str
    phone_number: str
    location: str
    external_id: str | None
    target_metadata: dict


def _parse_import_csv(content: bytes) -> tuple[list[_ImportRow], list[ImportRowError]]:
    """Decode and validate the upload. Pure CPU work — run off the event loop."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))
    raw_rows = list(reader)

    if not raw_rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV has no data rows")

    headers = {h.lower().strip() for h in (reader.fieldnames or [])}
    missing = _REQUIRED_FIELDS - headers
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV missing required columns: {', '.join(sorted(missing))}",
        )

    parsed: list[_ImportRow] = []
    errors: list[ImportRowError] = []

    for idx, raw_row in enumerate(raw_rows):
        row_num = idx + 2  # 1-based, +1 for header

        # DictReader parks unmatched trailing cells under the None restkey and
        # hands back a list for them; either shape means a ragged row.
        if None in raw_row or any(isinstance(v, list) for v in raw_row.values()):
            errors.append(ImportRowError(
                row=row_num,
                error="row has more columns than the header",
            ))
            continue

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
            phone = to_us_e164(row["phone_number"])
        except ValueError as exc:
            errors.append(ImportRowError(
                row=row_num,
                error=f"invalid phone number: {_csv_cell(row['phone_number'])} — {exc}",
            ))
            continue

        external_id = row.get("external_id") or None

        # Validate field lengths against the column widths
        values = {
            "name": row["name"],
            "title": row["title"],
            "phone_number": phone,
            "location": row["location"],
            "external_id": external_id or "",
        }
        over_long = [
            f"{field} exceeds {MAX_LENGTHS[field]} characters"
            for field, value in values.items()
            if len(value) > MAX_LENGTHS[field]
        ]
        if over_long:
            errors.append(ImportRowError(row=row_num, error="; ".join(over_long)))
            continue

        extra_cols = {k: v for k, v in row.items() if k not in _KNOWN_FIELDS and v}

        parsed.append(_ImportRow(
            name=row["name"],
            title=row["title"],
            phone_number=phone,
            location=row["location"],
            external_id=external_id,
            target_metadata=extra_cols if extra_cols else {},
        ))

    return parsed, errors


async def _do_import(
    campaign_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession,
    redis: object,
) -> ImportResult:
    """Core import logic — called inside the per-campaign Redis lock."""
    content = await read_upload_limited(file, _MAX_CSV_BYTES)

    if content is None:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 5 MB limit")

    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")

    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()
    if not filename.endswith(".csv") and "csv" not in content_type and "text/plain" not in content_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a CSV")

    parsed_rows, errors = await asyncio.to_thread(_parse_import_csv, content)

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

    next_order = await _next_order(campaign_id, db)

    new_targets: list[Target] = []
    updated_count = 0

    for row in parsed_rows:
        # Upsert: update existing if external_id matches. Targets built earlier in
        # this file join the map too, so a repeated external_id updates the pending
        # row rather than inserting a second one.
        if row.external_id and row.external_id in existing_by_ext_id:
            existing = existing_by_ext_id[row.external_id]
            existing.name = row.name
            existing.title = row.title
            existing.phone_number = row.phone_number
            existing.location = row.location
            existing.target_metadata = row.target_metadata
            updated_count += 1
        else:
            target = Target(
                name=row.name,
                title=row.title,
                phone_number=row.phone_number,
                location=row.location,
                external_id=row.external_id,
                target_metadata=row.target_metadata,
            )
            new_targets.append(target)
            if row.external_id:
                existing_by_ext_id[row.external_id] = target

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
            ex=_IMPORT_ERRORS_TTL_SECONDS,
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
    token = secrets.token_hex(8)
    locked = await redis.set(lock_key, token, nx=True, ex=_IMPORT_LOCK_TTL_SECONDS)
    if not locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An import is already in progress for this campaign. Please wait and try again.",
        )

    try:
        return await _do_import(campaign_id, file, db, redis)
    finally:
        await redis.eval(RELEASE_IF_OWNER, 1, lock_key, token)


@router.get("/{campaign_id}/targets/import-errors")
async def download_import_errors(
    campaign_id: uuid.UUID,
    _: AdminUser,
    db: DB,
) -> Response:
    """Download the last import's error rows as a CSV file.

    Cells are exported as inert text: a value that a spreadsheet would evaluate
    as a formula is quoted first.
    """
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
        writer.writerow([_csv_cell(e["row"]), _csv_cell(e["error"])])

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

    next_order = await _next_order(campaign.id, db)

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
    """Detach a target from a campaign, deleting the row only when nothing else needs it.

    A target still attached to another campaign, referenced by a logged Call,
    or queued in a call that is happening right now is kept: call history keeps
    resolving to a named official, and a supporter mid-session still hears the
    official they were promised.
    """
    target, ct = await _get_target_in_campaign_or_404(campaign_id, target_id, db)

    await db.delete(ct)
    await db.flush()

    other_campaigns = await db.scalar(
        select(func.count())
        .select_from(CampaignTarget)
        .where(CampaignTarget.target_id == target_id)
    )
    logged_calls = await db.scalar(
        select(func.count()).select_from(Call).where(Call.target_id == target_id)
    )

    in_a_live_call = False
    if not other_campaigns and not logged_calls:
        # Call state lives in Redis under call_session:{session_id} and holds the
        # target_ids the session will still dial. SCAN is bounded by the sessions
        # alive inside the 2-hour state TTL, and only runs when the row would
        # otherwise be deleted.
        redis = get_redis()
        wanted = str(target_id)
        async for key in redis.scan_iter(match="call_session:*", count=100):
            raw = await redis.get(key)
            if not raw:
                continue
            try:
                live_state = json.loads(raw)
            except ValueError:
                continue
            if wanted in (live_state.get("target_ids") or []):
                in_a_live_call = True
                logger.info(
                    "target %s detached from campaign %s but kept: a live call still dials it",
                    wanted,
                    campaign_id,
                )
                break

    if not other_campaigns and not logged_calls and not in_a_live_call:
        await db.delete(target)

    campaign = await get_campaign_or_404(campaign_id, db)
    campaign.updated_at = datetime.now(timezone.utc)
    await db.commit()
