"""CORS policy split between the public embed API and the admin API."""

import uuid

import pytest
from httpx import AsyncClient

from app.config import settings
from app.main import is_public_path

ADMIN_ORIGINS = [o.strip() for o in settings.ADMIN_CORS_ORIGINS.split(",") if o.strip()]
FOREIGN_ORIGIN = "https://not-the-dashboard.example"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000/public",
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000/count",
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000/reps",
        "/api/v1/calls/create",
        "/api/v1/tokens/voice",
        "/static/powerline-embed.iife.js",
    ],
)
def test_public_paths_are_recognised(path: str) -> None:
    assert is_public_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/campaigns",
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000",
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000/checklist",
        "/api/v1/campaigns/00000000-0000-0000-0000-000000000000/targets",
        "/api/v1/users",
        "/api/v1/users/me",
        "/api/v1/analytics/overview",
    ],
)
def test_admin_paths_are_not_public(path: str) -> None:
    assert not is_public_path(path)


async def test_public_endpoint_allows_any_origin(client: AsyncClient) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/public",
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_admin_endpoint_refuses_an_unlisted_origin(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get(
        "/api/v1/users/me",
        headers={**admin_headers, "Origin": FOREIGN_ORIGIN},
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


@pytest.mark.skipif(not ADMIN_ORIGINS, reason="ADMIN_CORS_ORIGINS is empty")
async def test_admin_endpoint_allows_a_listed_origin(
    client: AsyncClient, admin_headers: dict
) -> None:
    origin = ADMIN_ORIGINS[0]
    resp = await client.get(
        "/api/v1/users/me",
        headers={**admin_headers, "Origin": origin},
    )
    assert resp.headers.get("access-control-allow-origin") == origin


async def test_admin_origin_is_not_granted_on_public_paths_only(
    client: AsyncClient,
) -> None:
    """The admin policy must never be the one answering an embed request."""
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/public",
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert resp.headers.get("access-control-allow-origin") != FOREIGN_ORIGIN
