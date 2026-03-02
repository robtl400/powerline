"""Smoke tests for campaign and target endpoints."""

import uuid

from httpx import AsyncClient

from app.models.campaign import Campaign
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


async def test_campaigns_require_admin(
    client: AsyncClient, staff_headers: dict
) -> None:
    resp = await client.get("/api/v1/campaigns", headers=staff_headers)
    assert resp.status_code == 403


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
