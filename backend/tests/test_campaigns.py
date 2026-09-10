"""Smoke tests for campaign and target endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.models.user import User


async def test_create_campaign(
    client: AsyncClient, admin_user: User, admin_headers: dict
) -> None:
    name = f"New Campaign {uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/v1/campaigns", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == name
    assert data["status"] == "draft"
    assert data["target_count"] == 0
    # Campaign cleanup is handled by the admin_user FK cascade (SET NULL on delete)
    # and will be cleaned up in subsequent runs via unique names.


async def test_list_campaigns(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/campaigns", headers=admin_headers)
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert str(campaign.id) in ids


async def test_get_campaign(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(campaign.id)
    assert resp.json()["targets"] == []


async def test_campaign_not_found(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404


async def test_valid_status_transition(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    # draft -> live is valid
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"status": "live"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "live"


async def test_invalid_status_transition(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    # draft -> archived is NOT a valid transition
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"status": "archived"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_add_and_remove_target(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Rep Smith",
            "title": "Representative",
            "phone_number": "+12025551234",
            "location": "CA-12",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    target_id = resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}",
        headers=admin_headers,
    )
    assert del_resp.status_code == 204


async def test_reorder_targets(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    t1 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Target One",
            "title": "Rep",
            "phone_number": "+12025550001",
            "location": "WA-07",
        },
        headers=admin_headers,
    )
    t2 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Target Two",
            "title": "Sen",
            "phone_number": "+12025550002",
            "location": "WA",
        },
        headers=admin_headers,
    )
    tid1 = t1.json()["id"]
    tid2 = t2.json()["id"]

    # Reorder: put t2 before t1
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}/targets/reorder",
        json={"target_ids": [tid2, tid1]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["id"] == tid2
    assert reordered[1]["id"] == tid1
    # Targets and CampaignTargets are cleaned up by the campaign fixture teardown.


async def test_campaigns_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 401


async def test_staff_can_read_campaigns(
    client: AsyncClient, campaign: Campaign, staff_headers: dict
) -> None:
    """Staff see the campaign list, one campaign, and its checklist."""
    listed = await client.get("/api/v1/campaigns", headers=staff_headers)
    assert listed.status_code == 200

    detail = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=staff_headers)
    assert detail.status_code == 200

    checklist = await client.get(
        f"/api/v1/campaigns/{campaign.id}/checklist", headers=staff_headers
    )
    assert checklist.status_code == 200


async def test_campaign_writes_require_admin(
    client: AsyncClient, campaign: Campaign, staff_headers: dict
) -> None:
    """Reads are open to staff; anything that changes a campaign is not."""
    created = await client.post(
        "/api/v1/campaigns",
        json={"name": "Staff Attempt"},
        headers=staff_headers,
    )
    assert created.status_code == 403

    patched = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"name": "Renamed by staff"},
        headers=staff_headers,
    )
    assert patched.status_code == 403


async def test_target_invalid_phone(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Rep X",
            "title": "Rep",
            "phone_number": "not-a-phone",
            "location": "CA",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Enum-valued inputs are rejected at validation, not at the database
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"campaign_type": "not_a_type"},
    {"target_ordering": "backwards"},
    {"language": "en-US-extended"},
])
async def test_create_campaign_rejects_bad_enum(
    client: AsyncClient, admin_headers: dict, payload: dict
) -> None:
    body = {"name": f"Bad Enum {uuid.uuid4().hex[:8]}", **payload}
    resp = await client.post("/api/v1/campaigns", json=body, headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.parametrize("payload", [
    {"campaign_type": "not_a_type"},
    {"target_ordering": "backwards"},
    {"language": "en-US-extended"},
    {"status": "retired"},
])
async def test_update_campaign_rejects_bad_enum(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, payload: dict
) -> None:
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}", json=payload, headers=admin_headers
    )
    assert resp.status_code == 422


async def test_list_campaigns_rejects_bad_status_filter(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/campaigns?status=retired", headers=admin_headers)
    assert resp.status_code == 422


async def test_list_campaigns_pagination(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """skip/limit are honoured and the response stays a bare list."""
    page = await client.get("/api/v1/campaigns?skip=0&limit=1", headers=admin_headers)
    assert page.status_code == 200
    assert isinstance(page.json(), list)
    assert len(page.json()) <= 1

    assert (
        await client.get("/api/v1/campaigns?limit=501", headers=admin_headers)
    ).status_code == 422


# ---------------------------------------------------------------------------
# remove_target: detach, then delete only when nothing else references it
# ---------------------------------------------------------------------------

async def test_remove_target_deletes_unreferenced_target(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Lonely Target",
            "title": "Rep",
            "phone_number": "+12025557001",
            "location": "CA-01",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert await db.get(Target, target_id) is None


async def test_remove_target_keeps_target_with_call_history(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    """A target a Call points at survives removal so history stays readable."""
    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Historic Target",
            "title": "Senator",
            "phone_number": "+12025557002",
            "location": "WA",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])

    session = CallSession(
        campaign_id=campaign.id,
        connection_type="outbound_phone",
        twilio_call_sid=f"CAhist{uuid.uuid4().hex[:20]}",
        status="completed",
    )
    db.add(session)
    await db.flush()
    call = Call(
        session_id=session.id,
        campaign_id=campaign.id,
        target_id=target_id,
        twilio_call_sid=f"CAleg{uuid.uuid4().hex[:20]}",
        status="completed",
    )
    db.add(call)
    await db.commit()

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204

    survivor = await db.get(Target, target_id)
    assert survivor is not None

    ct_left = await db.scalar(
        select(func.count())
        .select_from(CampaignTarget)
        .where(CampaignTarget.target_id == target_id)
    )
    assert ct_left == 0

    await db.execute(delete(Call).where(Call.id == call.id))
    await db.execute(delete(CallSession).where(CallSession.id == session.id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


async def test_remove_target_keeps_target_shared_with_another_campaign(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_user: User,
    admin_headers: dict,
) -> None:
    """A target still attached elsewhere is only detached, never deleted."""
    other = Campaign(
        name=f"Other Campaign {uuid.uuid4().hex[:8]}", created_by_id=admin_user.id
    )
    db.add(other)
    await db.flush()

    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Shared Target",
            "title": "Rep",
            "phone_number": "+12025557003",
            "location": "NY-10",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])
    db.add(CampaignTarget(campaign_id=other.id, target_id=target_id, order=0))
    await db.commit()

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert await db.get(Target, target_id) is not None

    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target_id))
    await db.execute(delete(Campaign).where(Campaign.id == other.id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()
