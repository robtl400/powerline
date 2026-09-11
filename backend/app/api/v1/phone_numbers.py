import asyncio
import uuid

import structlog
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, CurrentUser, Provider
from app.models.campaign import Campaign
from app.models.campaign_phone_number import CampaignPhoneNumber
from app.models.phone_number import PhoneNumber
from app.schemas.common import Page
from app.schemas.phone_number import CampaignAssignRequest, PhoneNumberResponse

log = structlog.get_logger()

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])

DEFAULT_PAGE_LIMIT = 200
MAX_PAGE_LIMIT = 500


async def _get_phone_or_404(phone_id: uuid.UUID, db: AsyncSession) -> PhoneNumber:
    result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id))
    pn = result.scalar_one_or_none()
    if not pn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    return pn


# NOTE: /sync must be registered BEFORE /{phone_id} — FastAPI matches routes in
# registration order, and "sync" would otherwise be parsed as a UUID path param.
@router.post("/sync", response_model=Page[PhoneNumberResponse])
async def sync_phone_numbers(
    _: AdminUser,
    db: DB,
    provider: Provider,
) -> Page[PhoneNumberResponse]:
    """Fetch all phone numbers from Twilio and upsert into the local database.

    Idempotent — safe to call repeatedly. Numbers are matched by twilio_sid.
    `total` counts every number synced; `items` carries at most one page of them.
    """
    loop = asyncio.get_running_loop()
    try:
        twilio_numbers = await loop.run_in_executor(None, provider.list_phone_numbers)
    except Exception:
        log.exception("twilio_list_numbers_failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch numbers from Twilio")

    sids = [info.sid for info in twilio_numbers]
    known: dict[str, PhoneNumber] = {}
    if sids:
        rows = await db.execute(select(PhoneNumber).where(PhoneNumber.twilio_sid.in_(sids)))
        known = {pn.twilio_sid: pn for pn in rows.scalars().all()}

    results: list[PhoneNumber] = []

    for info in twilio_numbers:
        pn = known.get(info.sid)

        if pn:
            pn.number = info.number
            pn.label = info.label
            pn.capabilities = info.capabilities
        else:
            pn = PhoneNumber(
                number=info.number,
                twilio_sid=info.sid,
                provider="twilio",
                label=info.label,
                capabilities=info.capabilities,
                trust_status="unknown",
            )
            db.add(pn)
            known[info.sid] = pn

        results.append(pn)

    await db.commit()

    log.info("phone_numbers_synced", count=len(results))
    return Page[PhoneNumberResponse](
        total=len(results),
        items=[
            PhoneNumberResponse.model_validate(pn) for pn in results[:DEFAULT_PAGE_LIMIT]
        ],
    )


@router.get("", response_model=Page[PhoneNumberResponse])
async def list_phone_numbers(
    _: CurrentUser,
    db: DB,
    skip: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
) -> Page[PhoneNumberResponse]:
    total = await db.scalar(select(func.count()).select_from(PhoneNumber))
    result = await db.execute(
        select(PhoneNumber)
        .order_by(PhoneNumber.created_at.desc(), PhoneNumber.id)
        .offset(skip)
        .limit(limit)
    )
    return Page[PhoneNumberResponse](
        total=int(total or 0),
        items=[PhoneNumberResponse.model_validate(pn) for pn in result.scalars().all()],
    )


@router.post("/{phone_id}/assign", response_model=PhoneNumberResponse)
async def assign_phone_to_campaign(
    phone_id: uuid.UUID,
    body: CampaignAssignRequest,
    _: AdminUser,
    db: DB,
) -> PhoneNumber:
    """Assign a phone number to a campaign. A number can serve multiple campaigns.

    Idempotent — an assignment that already exists, including one written by a
    concurrent request, answers with the phone number unchanged.
    """
    pn = await _get_phone_or_404(phone_id, db)

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == body.campaign_id)
    )
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    db.add(CampaignPhoneNumber(
        campaign_id=body.campaign_id,
        phone_number_id=phone_id,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        pn = await _get_phone_or_404(phone_id, db)

    return pn
