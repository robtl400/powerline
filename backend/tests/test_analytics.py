"""Tests for the analytics filter validation surface."""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.campaign import Campaign

_ROUTES = ["calls", "calls/export"]


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("query", [
    "status=retired",
    "status=busy",
    "connection_type=carrier_pigeon",
    "connection_type=webrtc_v2",
])
async def test_bad_filter_values_are_rejected(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, route: str, query: str
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/{route}?{query}", headers=admin_headers
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("query", [
    "status=completed",
    "status=in_progress",
    "connection_type=webrtc",
    "connection_type=inbound_phone",
])
async def test_valid_filter_values_are_accepted(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, route: str, query: str
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/{route}?{query}", headers=admin_headers
    )
    assert resp.status_code == 200


async def test_unknown_campaign_still_404s(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/calls?status=completed", headers=admin_headers
    )
    assert resp.status_code == 404
