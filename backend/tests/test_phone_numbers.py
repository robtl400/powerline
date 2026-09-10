"""Phone number sync, listing, and campaign assignment.

The telephony provider is replaced through dependency_overrides so no test
reaches the Twilio API.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_telephony_provider
from app.main import app
from app.models.campaign import Campaign
from app.models.campaign_phone_number import CampaignPhoneNumber
from app.models.phone_number import PhoneNumber
from app.services.telephony.base import PhoneNumberInfo

VOICE_ONLY = {"voice": True, "sms": False, "mms": False}
VOICE_AND_SMS = {"voice": True, "sms": True, "mms": False}


def _info(sid: str, number: str, label: str, capabilities: dict) -> PhoneNumberInfo:
    return PhoneNumberInfo(
        sid=sid,
        number=number,
        label=label,
        capabilities=capabilities,
        trust_status="unknown",
    )


@pytest.fixture
async def provider() -> AsyncGenerator[MagicMock, None]:
    """Install a mock telephony provider for the duration of one test."""
    mock = MagicMock()
    mock.list_phone_numbers.return_value = []
    app.dependency_overrides[get_telephony_provider] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_telephony_provider, None)


@pytest.fixture
async def sids(db: AsyncSession) -> AsyncGenerator[Callable[[], str], None]:
    """Hand out unique Twilio SIDs and delete every row created under them."""
    issued: list[str] = []

    def _issue() -> str:
        sid = f"PN{uuid.uuid4().hex[:32]}"
        issued.append(sid)
        return sid

    yield _issue

    if issued:
        ids = (
            await db.execute(select(PhoneNumber.id).where(PhoneNumber.twilio_sid.in_(issued)))
        ).scalars().all()
        if ids:
            await db.execute(
                delete(CampaignPhoneNumber).where(CampaignPhoneNumber.phone_number_id.in_(ids))
            )
            await db.execute(delete(PhoneNumber).where(PhoneNumber.id.in_(ids)))
            await db.commit()


def _number() -> str:
    return f"+1{uuid.uuid4().int % 10**10:010d}"


# ---------------------------------------------------------------------------
# POST /phone-numbers/sync
# ---------------------------------------------------------------------------


async def test_sync_inserts_new_numbers(
    client: AsyncClient,
    db: AsyncSession,
    admin_headers: dict,
    provider: MagicMock,
    sids: Callable[[], str],
) -> None:
    sid, number = sids(), _number()
    provider.list_phone_numbers.return_value = [_info(sid, number, "Main line", VOICE_ONLY)]

    resp = await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert len(body) == 1
    assert body[0]["twilio_sid"] == sid
    assert body[0]["number"] == number
    assert body[0]["label"] == "Main line"
    assert body[0]["capabilities"] == VOICE_ONLY
    assert body[0]["trust_status"] == "unknown"
    assert body[0]["provider"] == "twilio"

    stored = await db.scalar(select(PhoneNumber).where(PhoneNumber.twilio_sid == sid))
    assert stored is not None


async def test_second_sync_updates_in_place(
    client: AsyncClient,
    db: AsyncSession,
    admin_headers: dict,
    provider: MagicMock,
    sids: Callable[[], str],
) -> None:
    """Matching on twilio_sid refreshes the row instead of adding a second one."""
    sid, number = sids(), _number()
    provider.list_phone_numbers.return_value = [_info(sid, number, "Before", VOICE_ONLY)]
    first = await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    assert first.status_code == 200, first.text

    provider.list_phone_numbers.return_value = [_info(sid, number, "After", VOICE_AND_SMS)]
    second = await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    assert second.status_code == 200, second.text
    assert second.json()[0]["id"] == first.json()[0]["id"]
    assert second.json()[0]["label"] == "After"
    assert second.json()[0]["capabilities"] == VOICE_AND_SMS

    rows = await db.scalar(
        select(func.count()).select_from(PhoneNumber).where(PhoneNumber.twilio_sid == sid)
    )
    assert rows == 1


async def test_sync_returns_502_when_the_provider_fails(
    client: AsyncClient, admin_headers: dict, provider: MagicMock
) -> None:
    provider.list_phone_numbers.side_effect = RuntimeError("twilio is down")

    resp = await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Failed to fetch numbers from Twilio"


async def test_sync_is_admin_only(
    client: AsyncClient, staff_headers: dict, provider: MagicMock
) -> None:
    resp = await client.post("/api/v1/phone-numbers/sync", headers=staff_headers)
    assert resp.status_code == 403
    assert provider.list_phone_numbers.call_count == 0


# ---------------------------------------------------------------------------
# GET /phone-numbers
# ---------------------------------------------------------------------------


async def test_list_returns_synced_numbers_newest_first(
    client: AsyncClient,
    admin_headers: dict,
    provider: MagicMock,
    sids: Callable[[], str],
) -> None:
    infos = [_info(sids(), _number(), f"Line {i}", VOICE_ONLY) for i in range(2)]
    provider.list_phone_numbers.return_value = infos
    assert (
        await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    ).status_code == 200

    listed = await client.get("/api/v1/phone-numbers?limit=500", headers=admin_headers)
    assert listed.status_code == 200
    listed_sids = [row["twilio_sid"] for row in listed.json()]
    assert all(info.sid in listed_sids for info in infos)

    page = await client.get("/api/v1/phone-numbers?skip=0&limit=1", headers=admin_headers)
    assert page.status_code == 200
    assert len(page.json()) == 1


async def test_list_is_open_to_staff(client: AsyncClient, staff_headers: dict) -> None:
    resp = await client.get("/api/v1/phone-numbers", headers=staff_headers)
    assert resp.status_code == 200


async def test_list_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/phone-numbers")).status_code == 401


# ---------------------------------------------------------------------------
# POST /phone-numbers/{id}/assign
# ---------------------------------------------------------------------------


@pytest.fixture
async def phone(
    client: AsyncClient,
    admin_headers: dict,
    provider: MagicMock,
    sids: Callable[[], str],
) -> str:
    provider.list_phone_numbers.return_value = [
        _info(sids(), _number(), "Assignable", VOICE_ONLY)
    ]
    resp = await client.post("/api/v1/phone-numbers/sync", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()[0]["id"]


async def test_assign_links_the_number_to_the_campaign(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    phone: str,
) -> None:
    resp = await client.post(
        f"/api/v1/phone-numbers/{phone}/assign",
        headers=admin_headers,
        json={"campaign_id": str(campaign.id)},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == phone

    links = await db.scalar(
        select(func.count())
        .select_from(CampaignPhoneNumber)
        .where(CampaignPhoneNumber.campaign_id == campaign.id)
    )
    assert links == 1


async def test_assign_twice_is_idempotent(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    phone: str,
) -> None:
    body = {"campaign_id": str(campaign.id)}
    first = await client.post(
        f"/api/v1/phone-numbers/{phone}/assign", headers=admin_headers, json=body
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/api/v1/phone-numbers/{phone}/assign", headers=admin_headers, json=body
    )
    assert second.status_code == 200, second.text

    links = await db.scalar(
        select(func.count())
        .select_from(CampaignPhoneNumber)
        .where(CampaignPhoneNumber.campaign_id == campaign.id)
    )
    assert links == 1


async def test_assign_unknown_phone_is_404(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/phone-numbers/{uuid.uuid4()}/assign",
        headers=admin_headers,
        json={"campaign_id": str(campaign.id)},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Phone number not found"


async def test_assign_unknown_campaign_is_404(
    client: AsyncClient, admin_headers: dict, phone: str
) -> None:
    resp = await client.post(
        f"/api/v1/phone-numbers/{phone}/assign",
        headers=admin_headers,
        json={"campaign_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Campaign not found"


async def test_assign_is_admin_only(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    staff_headers: dict,
    phone: str,
) -> None:
    resp = await client.post(
        f"/api/v1/phone-numbers/{phone}/assign",
        headers=staff_headers,
        json={"campaign_id": str(campaign.id)},
    )
    assert resp.status_code == 403

    links = await db.scalar(
        select(func.count())
        .select_from(CampaignPhoneNumber)
        .where(CampaignPhoneNumber.campaign_id == campaign.id)
    )
    assert links == 0
