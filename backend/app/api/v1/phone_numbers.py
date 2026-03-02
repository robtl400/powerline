import asyncio
import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, AdminUser, Provider
from app.models.campaign import Campaign
from app.models.campaign_phone_number import CampaignPhoneNumber
from app.models.phone_number import PhoneNumber
from app.schemas.phone_number import CampaignAssignRequest, PhoneNumberResponse

log = structlog.get_logger()

router = APIRouter(prefix="/phone-numbers", tags=["phone-numbers"])


def _to_response(pn: PhoneNumber) -> PhoneNumberResponse:
    return PhoneNumberResponse(
        id=pn.id,
        created_at=pn.created_at,
        number=pn.number,
        twilio_sid=pn.twilio_sid,
        provider=pn.provider,
        label=pn.label,
        capabilities=pn.capabilities,
        trust_status=pn.trust_status,
        trust_product_sid=pn.trust_product_sid,
    )


async def _get_phone_or_404(phone_id: uuid.UUID, db: AsyncSession) -> PhoneNumber:
    result = await db.execute(select(PhoneNumber).where(PhoneNumber.id == phone_id))
    pn = result.scalar_one_or_none()
    if not pn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phone number not found")
    return pn


# NOTE: /sync must be registered BEFORE /{phone_id} — FastAPI matches routes in
# registration order, and "sync" would otherwise be parsed as a UUID path param.
@router.post("/sync", response_model=list[PhoneNumberResponse])
async def sync_phone_numbers(
    _: AdminUser,
    db: DB,
    provider: Provider,
) -> list[PhoneNumberResponse]:
    """Fetch all phone numbers from Twilio and upsert into the local database.

    Idempotent — safe to call repeatedly. Numbers are matched by twilio_sid.
    """
    loop = asyncio.get_running_loop()
    try:
        twilio_numbers = await loop.run_in_executor(None, provider.list_phone_numbers)
    except Exception:
        log.exception("twilio_list_numbers_failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch numbers from Twilio")

    results: list[PhoneNumber] = []

    for info in twilio_numbers:
        existing = await db.execute(
            select(PhoneNumber).where(PhoneNumber.twilio_sid == info.sid)
        )
        pn = existing.scalar_one_or_none()

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

        results.append(pn)

    await db.commit()
    for pn in results:
        await db.refresh(pn)

    log.info("phone_numbers_synced", count=len(results))
    return [_to_response(pn) for pn in results]


@router.get("", response_model=list[PhoneNumberResponse])
async def list_phone_numbers(
    _: AdminUser,
    db: DB,
) -> list[PhoneNumberResponse]:
    result = await db.execute(
        select(PhoneNumber).order_by(PhoneNumber.created_at.desc())
    )
    return [_to_response(pn) for pn in result.scalars().all()]


@router.post("/{phone_id}/assign", response_model=PhoneNumberResponse)
async def assign_phone_to_campaign(
    phone_id: uuid.UUID,
    body: CampaignAssignRequest,
    _: AdminUser,
    db: DB,
) -> PhoneNumberResponse:
    """Assign a phone number to a campaign. A number can serve multiple campaigns.

    Idempotent — if the assignment already exists, returns the phone number unchanged.
    """
    pn = await _get_phone_or_404(phone_id, db)

    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == body.campaign_id)
    )
    if not campaign_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    existing = await db.execute(
        select(CampaignPhoneNumber).where(
            CampaignPhoneNumber.campaign_id == body.campaign_id,
            CampaignPhoneNumber.phone_number_id == phone_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(CampaignPhoneNumber(
            campaign_id=body.campaign_id,
            phone_number_id=phone_id,
        ))
        await db.commit()

    return _to_response(pn)
