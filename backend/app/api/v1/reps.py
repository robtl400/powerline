from __future__ import annotations

import re
import uuid

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB
from app.config import settings
from app.dependencies import get_client_ip
from app.models.campaign import Campaign
from app.redis_client import get_redis
from app.services.civic.google_civic import MissingApiKeyError
from app.services.civic_service import issue_rep_tokens, lookup_reps
from app.services.rate_limiter import check_rate_limit

log = structlog.get_logger()

router = APIRouter(prefix="/campaigns", tags=["reps"])

_ZIP_RE = re.compile(r"^\d{5}$")

_NO_REPS_DEFAULT = (
    "We couldn't find a representative for your zip code. "
    "You may enter a phone number manually."
)


class RepInfoOut(BaseModel):
    name: str
    title: str
    level: str
    # Opaque handle the call endpoints exchange for the rep's phone number.
    rep_token: str


class RepsResponse(BaseModel):
    reps: list[RepInfoOut]
    message: str | None = None


@router.get("/{campaign_id}/reps", response_model=RepsResponse)
async def get_reps(
    campaign_id: uuid.UUID,
    request: Request,
    db: DB,
    zip: str = Query(..., description="5-digit US ZIP code"),
) -> RepsResponse:
    """
    Look up elected representatives for a ZIP code.

    Public endpoint — no auth required. Same access pattern as GET /campaigns/{id}/public.
    Rate limited per client IP and per campaign so the upstream civic APIs cannot
    be drained by an unauthenticated caller.
    """
    await check_rate_limit(get_redis(), "reps", get_client_ip(request), settings.REPS_RATE_LIMIT)

    if not _ZIP_RE.match(zip):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="zip must be a 5-digit US postal code",
        )

    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign or campaign.status != "live":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active")

    await check_rate_limit(
        get_redis(),
        "reps-campaign",
        str(campaign_id),
        settings.REPS_RATE_LIMIT * 25,
    )

    embed_config: dict = campaign.embed_config or {}

    try:
        reps = await lookup_reps(zip, str(campaign.id), embed_config)
    except MissingApiKeyError as exc:
        log.warning("reps_missing_api_key", campaign_id=str(campaign_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Representative lookup is temporarily unavailable.", "fallback": "manual_entry"},
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            retry_after = exc.response.headers.get("Retry-After", "60")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "Rate limit reached. Please try again shortly.", "fallback": "manual_entry"},
                headers={"Retry-After": retry_after},
            )
        log.error("reps_api_http_error", campaign_id=str(campaign_id), status=exc.response.status_code)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Representative lookup failed.", "fallback": "manual_entry"},
        )
    except Exception:
        log.exception("reps_lookup_unexpected", campaign_id=str(campaign_id))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"message": "Representative lookup failed.", "fallback": "manual_entry"},
        )

    if not reps:
        return RepsResponse(
            reps=[],
            message=embed_config.get("no_reps_message", _NO_REPS_DEFAULT),
        )

    requested_levels = set(embed_config.get("target_levels", ["federal"]))
    returned_levels = {r["level"] for r in reps}
    missing_levels = requested_levels - returned_levels

    notice: str | None = None
    if missing_levels and reps:
        notice = "Note: some representatives may be temporarily unavailable."

    tokenized = await issue_rep_tokens(str(campaign_id), reps)

    return RepsResponse(
        reps=[
            RepInfoOut(
                name=r["name"],
                title=r["title"],
                level=r["level"],
                rep_token=r["rep_token"],
            )
            for r in tokenized
        ],
        message=notice,
    )
