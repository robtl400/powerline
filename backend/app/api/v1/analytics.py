"""Campaign analytics endpoints.

All routes are read-only and open to any signed-in user. Route registration
order is critical — specific sub-paths (/{id}/calls/export, /{id}/calls-by-date,
/{id}/stats, /{id}/quality) are registered before the wildcard-like /{id}/calls
to avoid any path ambiguity.
"""
from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.api.deps import DB, CurrentUser
from app.api.v1.helpers import get_campaign_or_404, local_timezone
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.target import Target
from app.schemas.analytics import (
    CallSessionPage,
    CallSessionRow,
    CampaignStatsResponse,
    DailyCount,
    QualityResponse,
    TargetStats,
)

router = APIRouter(prefix="/campaigns", tags=["analytics"])

SessionStatus = Literal["initiated", "in_progress", "completed", "failed"]
ConnectionType = Literal["webrtc", "outbound_phone", "inbound_phone"]

# Ceiling on rows written by the CSV export. Hitting it ends the file with a
# comment line so the caller can tell a truncated export from a complete one.
MAX_EXPORT_ROWS = 100_000

# Rows accumulate in a StringIO until it holds at least this many characters,
# then the buffer is drained into the response and reused.
EXPORT_CHUNK_CHARS = 32_768

# Stats and quality read a trailing window rather than a campaign's whole
# history, so an aggregate stays bounded as a campaign ages.
DEFAULT_WINDOW_DAYS = 30

# Rows in the per-target breakdown. The list is ordered by call volume, so the
# cap keeps the targets a campaign actually dialed.
MAX_PER_TARGET_ROWS = 100

# A target the supporter skipped was never dialed: it is not a completed call
# and it is not a failed one, so it stays out of the volume and quality
# aggregates and is reported in the status breakdowns instead.
SKIPPED = "skipped"

FAILURE_STATUSES = ["failed", "busy", "no_answer", "canceled", SKIPPED]

EXPORT_FIELDS = [
    "id",
    "created_at",
    "connection_type",
    "status",
    "call_count",
    "duration_seconds",
]


def _drain(buffer: io.StringIO) -> str:
    """Return everything written to ``buffer`` and reset it for reuse."""
    chunk = buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)
    return chunk


async def _stream_export_rows(
    db: AsyncSession, stmt: Select[Any]
) -> AsyncGenerator[str, None]:
    """Yield the export CSV chunk by chunk, reading the result set as it arrives.

    The AsyncSession comes from a dependency with ``yield``; FastAPI keeps that
    dependency's exit stack open around the sending of the response, so the
    session and its server-side cursor stay usable until the last chunk.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_FIELDS)
    writer.writeheader()
    yield _drain(buffer)

    cap = MAX_EXPORT_ROWS
    written = 0
    truncated = False

    result = await db.stream(stmt.limit(cap + 1))
    try:
        async for row in result:
            if written == cap:
                truncated = True
                break
            writer.writerow({
                "id": str(row.id),
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "connection_type": row.connection_type,
                "status": row.status,
                "call_count": row.call_count,
                "duration_seconds": row.duration or "",
            })
            written += 1
            if buffer.tell() >= EXPORT_CHUNK_CHARS:
                yield _drain(buffer)
    finally:
        await result.close()

    tail = _drain(buffer)
    if tail:
        yield tail
    if truncated:
        yield f"# truncated: export is limited to {cap} rows\n"


# ---------------------------------------------------------------------------
# GET /{id}/calls/export  — must be registered BEFORE /{id}/calls
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/calls/export")
async def export_calls_csv(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    status: SessionStatus | None = Query(default=None),
    connection_type: ConnectionType | None = Query(default=None),
    start: str | None = Query(default=None, description="ISO date, e.g. 2026-01-01"),
    end: str | None = Query(default=None, description="ISO date, e.g. 2026-03-01"),
) -> StreamingResponse:
    """Export call sessions as CSV. Accepts the same filters as GET /{id}/calls.

    Rows are streamed straight from the database cursor and capped at
    MAX_EXPORT_ROWS; a capped export ends with a `#` comment line saying so.
    """
    await get_campaign_or_404(campaign_id, db)

    stmt = (
        select(
            CallSession.id,
            CallSession.created_at,
            CallSession.connection_type,
            CallSession.status,
            CallSession.duration,
            func.count(Call.id).label("call_count"),
        )
        .outerjoin(Call, Call.session_id == CallSession.id)
        .where(CallSession.campaign_id == campaign_id)
        .group_by(CallSession.id)
        .order_by(CallSession.created_at.desc())
    )

    stmt = _apply_session_filters(stmt, status, connection_type, start, end)

    filename = f"calls-{campaign_id}.csv"
    return StreamingResponse(
        _stream_export_rows(db, stmt),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /{id}/calls-by-date
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/calls-by-date", response_model=list[DailyCount])
async def calls_by_date(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    start: str | None = Query(default=None, description="ISO date, e.g. 2026-01-01"),
    end: str | None = Query(default=None, description="ISO date, e.g. 2026-03-01"),
    granularity: str = Query(default="day", pattern="^(hour|day|week)$"),
) -> list[DailyCount]:
    """Return call session counts grouped by time period.

    Defaults to the last 30 days if no start/end provided.
    """
    await get_campaign_or_404(campaign_id, db)

    start_dt, end_dt = _window(start, end)

    trunc = func.date_trunc(
        granularity, func.timezone(local_timezone().key, CallSession.created_at)
    )
    result = await db.execute(
        select(trunc.label("period"), func.count().label("count"))
        .where(
            CallSession.campaign_id == campaign_id,
            CallSession.created_at >= start_dt,
            CallSession.created_at <= end_dt,
        )
        .group_by(trunc)
        .order_by(trunc)
    )
    return [
        DailyCount(date=row.period.date().isoformat() if granularity == "day" else row.period.isoformat(), count=row.count)
        for row in result.all()
    ]


# ---------------------------------------------------------------------------
# GET /{id}/stats
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/stats", response_model=CampaignStatsResponse)
async def campaign_stats(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    start: str | None = Query(default=None, description="ISO date, e.g. 2026-01-01"),
    end: str | None = Query(default=None, description="ISO date, e.g. 2026-03-01"),
) -> CampaignStatsResponse:
    """Return aggregated stats for the campaign's sessions in a date range.

    Defaults to the last 30 days, and takes the same start/end the call log
    takes. Session totals, the completion rate and the connection-type split
    all come from one grouped pass; the per-target breakdown is a second, and
    is capped at MAX_PER_TARGET_ROWS rows.
    """
    await get_campaign_or_404(campaign_id, db)
    start_dt, end_dt = _window(start, end)

    dialed = func.count(Call.id).filter(Call.status != SKIPPED)

    session_rows = (
        await db.execute(
            select(
                CallSession.connection_type,
                CallSession.status,
                func.count(func.distinct(CallSession.id)).label("sessions"),
                dialed.label("calls"),
            )
            .outerjoin(Call, Call.session_id == CallSession.id)
            .where(
                CallSession.campaign_id == campaign_id,
                CallSession.created_at >= start_dt,
                CallSession.created_at <= end_dt,
            )
            .group_by(CallSession.connection_type, CallSession.status)
        )
    ).all()

    total_sessions = sum(row.sessions for row in session_rows)
    completed_sessions = sum(row.sessions for row in session_rows if row.status == "completed")
    total_calls = sum(row.calls for row in session_rows)

    connection_type_breakdown: dict[str, int] = {}
    for row in session_rows:
        connection_type_breakdown[row.connection_type] = (
            connection_type_breakdown.get(row.connection_type, 0) + row.sessions
        )

    completion_rate = completed_sessions / total_sessions if total_sessions else 0.0
    avg_calls_per_session = total_calls / total_sessions if total_sessions else 0.0

    # Per-target breakdown: join calls → targets
    target_result = await db.execute(
        select(
            Target.id.label("target_id"),
            Target.name,
            dialed.label("total_calls"),
            func.count(Call.id).filter(Call.status == "completed").label("completed_calls"),
            func.count(Call.id).filter(Call.status == SKIPPED).label("skipped_calls"),
            func.avg(Call.duration).filter(Call.status != SKIPPED).label("avg_duration"),
        )
        .select_from(Call)
        .join(Target, Target.id == Call.target_id)
        .join(CallSession, CallSession.id == Call.session_id)
        .where(
            CallSession.campaign_id == campaign_id,
            CallSession.created_at >= start_dt,
            CallSession.created_at <= end_dt,
        )
        .group_by(Target.id, Target.name)
        .order_by(dialed.desc())
        .limit(MAX_PER_TARGET_ROWS)
    )

    per_target = [
        TargetStats(
            target_id=row.target_id,
            name=row.name,
            total_calls=row.total_calls,
            completed_calls=row.completed_calls,
            skipped_calls=row.skipped_calls,
            avg_duration_seconds=(
                float(row.avg_duration) if row.avg_duration is not None else None
            ),
        )
        for row in target_result.all()
    ]

    return CampaignStatsResponse(
        total_sessions=total_sessions,
        completed_sessions=completed_sessions,
        completion_rate=round(completion_rate, 4),
        avg_calls_per_session=round(avg_calls_per_session, 2),
        connection_type_breakdown=connection_type_breakdown,
        per_target=per_target,
    )


# ---------------------------------------------------------------------------
# GET /{id}/calls  — paginated call session log
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/calls", response_model=CallSessionPage)
async def list_campaign_calls(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=200),
    status: SessionStatus | None = Query(default=None),
    connection_type: ConnectionType | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> CallSessionPage:
    """Return paginated call sessions for a campaign."""
    await get_campaign_or_404(campaign_id, db)

    base_stmt = (
        select(
            CallSession.id,
            CallSession.created_at,
            CallSession.connection_type,
            CallSession.status,
            CallSession.duration,
            func.count(Call.id).label("call_count"),
        )
        .outerjoin(Call, Call.session_id == CallSession.id)
        .where(CallSession.campaign_id == campaign_id)
        .group_by(CallSession.id)
    )

    base_stmt = _apply_session_filters(base_stmt, status, connection_type, start, end)

    # The page's rows are one per session, so the total is a plain count of the
    # sessions the filters match rather than a count over the grouped join.
    count_stmt = _apply_session_filters(
        select(func.count())
        .select_from(CallSession)
        .where(CallSession.campaign_id == campaign_id),
        status,
        connection_type,
        start,
        end,
    )
    total: int = await db.scalar(count_stmt) or 0

    # Paginate
    items_stmt = base_stmt.order_by(CallSession.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(items_stmt)
    rows = result.all()

    items = [
        CallSessionRow(
            id=row.id,
            created_at=row.created_at,
            connection_type=row.connection_type,
            status=row.status,
            call_count=row.call_count,
            duration=row.duration,
        )
        for row in rows
    ]

    return CallSessionPage(total=total, items=items)


# ---------------------------------------------------------------------------
# GET /{id}/quality
# ---------------------------------------------------------------------------

@router.get("/{campaign_id}/quality", response_model=QualityResponse)
async def campaign_quality(
    campaign_id: uuid.UUID,
    _: CurrentUser,
    db: DB,
    start: str | None = Query(default=None, description="ISO date, e.g. 2026-01-01"),
    end: str | None = Query(default=None, description="ISO date, e.g. 2026-03-01"),
) -> QualityResponse:
    """Return call quality metrics for the campaign's sessions in a date range.

    Defaults to the last 30 days, and takes the same start/end the call log
    takes. Skipped targets were never dialed, so they are counted in the
    breakdown and nowhere else.
    """
    await get_campaign_or_404(campaign_id, db)
    start_dt, end_dt = _window(start, end)

    in_window = (
        CallSession.campaign_id == campaign_id,
        CallSession.created_at >= start_dt,
        CallSession.created_at <= end_dt,
    )

    # Quality metrics across the dialed Call records for this campaign
    quality_row = (
        await db.execute(
            select(
                func.count(Call.id).filter(Call.status != SKIPPED).label("total_calls"),
                func.count(Call.quality_score).label("calls_with_quality"),
                func.avg(Call.quality_score).label("avg_quality"),
            )
            .join(CallSession, CallSession.id == Call.session_id)
            .where(*in_window)
        )
    ).one()

    # Session completion rate
    session_rows = (
        await db.execute(
            select(CallSession.status, func.count().label("cnt"))
            .where(*in_window)
            .group_by(CallSession.status)
        )
    ).all()
    total_sessions = sum(row.cnt for row in session_rows)
    completed_sessions = sum(row.cnt for row in session_rows if row.status == "completed")
    connection_rate = completed_sessions / total_sessions if total_sessions else 0.0

    # Breakdown by call status, for every status that is not a connected call
    failure_result = await db.execute(
        select(Call.status, func.count().label("cnt"))
        .join(CallSession, CallSession.id == Call.session_id)
        .where(*in_window, Call.status.in_(FAILURE_STATUSES))
        .group_by(Call.status)
    )
    failure_breakdown = {row.status: row.cnt for row in failure_result.all()}

    return QualityResponse(
        total_calls=quality_row.total_calls or 0,
        calls_with_quality=quality_row.calls_with_quality or 0,
        avg_quality_score=(
            round(float(quality_row.avg_quality), 2)
            if quality_row.avg_quality is not None
            else None
        ),
        connection_rate=round(connection_rate, 4),
        failure_breakdown=failure_breakdown,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(value: str, end_of_day: bool = False) -> datetime:
    """Parse an ISO date or datetime into an aware datetime.

    A value with no offset is read in the configured reporting timezone, so a
    bare date is local midnight and its end_of_day is local 23:59:59.999.
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid date format: {value}")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=local_timezone())
    if end_of_day and "T" not in value:
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
    return dt


def _window(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    """Resolve a start/end pair into the range an aggregate reads.

    An absent bound falls back to the trailing DEFAULT_WINDOW_DAYS days, so no
    aggregate scans a campaign's whole history by default.
    """
    now = datetime.now(timezone.utc)
    start_dt = _parse_date(start) if start else now - timedelta(days=DEFAULT_WINDOW_DAYS)
    end_dt = _parse_date(end, end_of_day=True) if end else now
    return start_dt, end_dt


def _apply_session_filters(stmt, status, connection_type, start, end):
    """Apply common filters to a CallSession select statement."""
    if status:
        stmt = stmt.where(CallSession.status == status)
    if connection_type:
        stmt = stmt.where(CallSession.connection_type == connection_type)
    if start:
        stmt = stmt.where(CallSession.created_at >= _parse_date(start))
    if end:
        stmt = stmt.where(CallSession.created_at <= _parse_date(end, end_of_day=True))
    return stmt
