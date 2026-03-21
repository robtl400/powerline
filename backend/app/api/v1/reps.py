from __future__ import annotations

import re
import uuid

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB
from app.models.campaign import Campaign
from app.services.civic.google_civic import MissingApiKeyError
from app.services.civic_service import lookup_reps

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
    phone: str
    level: str


class RepsResponse(BaseModel):
    reps: list[RepInfoOut]
    message: str | None = None


@router.get("/{campaign_id}/reps", response_model=RepsResponse)
async def get_reps(
    campaign_id: uuid.UUID,
    db: DB,
    response: Response,
    zip: str = Query(..., description="5-digit US ZIP code"),
) -> RepsResponse:
    """
    Look up elected representatives for a ZIP code.

    Public endpoint — no auth required. Same access pattern as GET /campaigns/{id}/public.
    """
    if not _ZIP_RE.match(zip):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="zip must be a 5-digit US postal code",
        )

    result = await db.execute(select(Campaign).where(Campaign.id == campaign_id))
    campaign = result.scalar_one_or_none()
    if not campaign or campaign.status != "live":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or not active")

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
            response.headers["Retry-After"] = retry_after
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"message": "Rate limit reached. Please try again shortly.", "fallback": "manual_entry"},
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

    return RepsResponse(
        reps=[RepInfoOut(**r) for r in reps],
        message=notice,
    )
