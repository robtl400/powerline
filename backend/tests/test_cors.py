"""CORS policy split between the public embed API and the admin API."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.main import PathScopedCORSMiddleware, is_public_path


@pytest.fixture(autouse=True)
async def clear_public_rate_keys(redis) -> AsyncGenerator[None, None]:
    async def _clear() -> None:
        for scope in ("public", "count"):
            keys = [k async for k in redis.scan_iter(match=f"rate:{scope}:*")]
            if keys:
                await redis.delete(*keys)

    await _clear()
    yield
    await _clear()

FOREIGN_ORIGIN = "https://not-the-dashboard.example"
ADMIN_ORIGIN = "https://dashboard.powerline.example"


@pytest.fixture
async def scoped_client() -> AsyncGenerator[AsyncClient, None]:
    """A client over PathScopedCORSMiddleware with a non-empty admin origin list."""

    async def ok(request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    inner = Starlette(
        routes=[
            Route("/api/v1/users/me", ok),
            Route("/api/v1/campaigns/{campaign_id}/public", ok),
        ]
    )
    scoped = PathScopedCORSMiddleware(
        inner,
        public_origins=["*"],
        admin_origins=[ADMIN_ORIGIN],
    )
    async with AsyncClient(
        transport=ASGITransport(app=scoped), base_url="http://test"
    ) as c:
        yield c


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


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/users/../campaigns/00000000-0000-0000-0000-000000000000/public",
        "/api/v1/users/me/../../campaigns/x/count",
        "/api/v1/campaigns/x/public/../../../users/me",
        "/static/../api/v1/users/me",
        "/api/v1/..%2fcampaigns/x/public",
        "/..",
    ],
)
def test_paths_walking_upward_are_never_public(path: str) -> None:
    assert not is_public_path(path)


@pytest.mark.parametrize(
    "path",
    [
        "//api/v1/campaigns/x/public",
        "/api/v1//campaigns/x/count",
        "/api/v1/campaigns/x/./reps",
        "/static//powerline-embed.iife.js",
        "/api/v1//calls/create",
    ],
)
def test_redundant_separators_still_resolve_to_the_public_surface(path: str) -> None:
    assert is_public_path(path)


async def test_public_endpoint_allows_any_origin(client: AsyncClient) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/public",
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_admin_endpoint_allows_a_listed_origin(scoped_client: AsyncClient) -> None:
    resp = await scoped_client.get("/api/v1/users/me", headers={"Origin": ADMIN_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == ADMIN_ORIGIN


async def test_admin_endpoint_refuses_an_unlisted_origin(scoped_client: AsyncClient) -> None:
    resp = await scoped_client.get("/api/v1/users/me", headers={"Origin": FOREIGN_ORIGIN})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


async def test_public_endpoint_answers_any_origin_under_the_admin_list(
    scoped_client: AsyncClient,
) -> None:
    resp = await scoped_client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/public",
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


async def test_admin_origin_is_not_granted_on_public_paths_only(
    client: AsyncClient,
) -> None:
    """The admin policy must never be the one answering an embed request."""
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/public",
        headers={"Origin": FOREIGN_ORIGIN},
    )
    assert resp.headers.get("access-control-allow-origin") != FOREIGN_ORIGIN
