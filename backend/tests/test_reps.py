"""Tests for GET /api/v1/campaigns/{id}/reps."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.redis_client import get_redis
from app.services.civic.google_civic import MissingApiKeyError


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def clear_reps_rate_limit(redis):
    """Drop the shared per-IP reps bucket around every test in this module."""
    await redis.delete("rate:reps:127.0.0.1")
    yield
    await redis.delete("rate:reps:127.0.0.1")


@pytest.fixture
async def live_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    campaign.status = "live"
    campaign.embed_config = {"target_levels": ["federal"]}
    await db.commit()
    await db.refresh(campaign)
    return campaign


@pytest.fixture
def mock_lookup():
    """Patch lookup_reps in the reps router module."""
    with patch("app.api.v1.reps.lookup_reps", new_callable=AsyncMock) as m:
        yield m


_SAMPLE_REPS = [
    {"name": "Sen. Smith", "title": "U.S. Senator", "phone": "+12025550100", "level": "federal"},
]


# ── Test cases ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_returns_reps(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """Endpoint returns reps (cache hit is transparent — service is mocked at router level)."""
    mock_lookup.return_value = _SAMPLE_REPS
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["reps"]) == 1
    assert data["reps"][0]["name"] == "Sen. Smith"
    mock_lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_miss_calls_api_and_returns_reps(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """Cache miss triggers lookup; result returned to caller."""
    mock_lookup.return_value = [
        {"name": "Rep. Jones", "title": "U.S. Representative", "phone": "+12025550200", "level": "federal"},
    ]
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=10001")
    assert resp.status_code == 200
    data = resp.json()
    rep = data["reps"][0]
    assert rep["name"] == "Rep. Jones"
    assert "phone" not in rep
    assert rep["rep_token"]


@pytest.mark.asyncio
async def test_api_error_with_stale_cache_returns_cached_data(
    client: AsyncClient,
    live_campaign: Campaign,
) -> None:
    """When Redis has a cached result, endpoint returns it without calling lookup_reps."""
    stale = [{"name": "Stale Rep", "title": "Senator", "phone": "+12025550901", "level": "federal"}]

    redis = get_redis()
    await redis.set(
        f"reps:12345:{live_campaign.id}:federal",
        json.dumps(stale),
        ex=86400,
    )

    # lookup_reps is NOT mocked — the real function will see the cache hit and return early.
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=12345")
    assert resp.status_code == 200
    assert resp.json()["reps"][0]["name"] == "Stale Rep"


@pytest.mark.asyncio
async def test_cache_key_tracks_configured_levels(
    client: AsyncClient,
    db: AsyncSession,
    live_campaign: Campaign,
    redis,
) -> None:
    """Changing target_levels reads a different cache slot, not the old level set's reps."""
    federal_only = [
        {
            "name": "Federal Only",
            "title": "U.S. Senator",
            "phone": "+12025550300",
            "level": "federal",
        }
    ]
    federal_key = f"reps:54321:{live_campaign.id}:federal"
    both_key = f"reps:54321:{live_campaign.id}:federal+state"
    await redis.delete(federal_key, both_key)
    await redis.set(federal_key, json.dumps(federal_only), ex=86400)

    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=54321")
    assert resp.status_code == 200
    assert resp.json()["reps"][0]["name"] == "Federal Only"

    live_campaign.embed_config = {"target_levels": ["federal", "state"]}
    await db.commit()

    with patch("app.services.civic_service._router.lookup", new_callable=AsyncMock) as lookup:
        lookup.return_value = []
        resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=54321")

    assert resp.status_code == 200
    assert resp.json()["reps"] == []
    assert await redis.get(both_key) == "[]"
    assert json.loads(await redis.get(federal_key))[0]["name"] == "Federal Only"

    await redis.delete(federal_key, both_key)


@pytest.mark.asyncio
async def test_api_error_no_cache_returns_503_with_fallback(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """API error with no cache → 503 with fallback: manual_entry."""
    mock_lookup.side_effect = Exception("Civic API down")
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=99999")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["fallback"] == "manual_entry"


@pytest.mark.asyncio
async def test_zero_results_returns_200_with_message(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """Zero reps → 200 with empty list and a user-facing message."""
    mock_lookup.return_value = []
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=00501")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reps"] == []
    assert "message" in data
    assert data["message"]  # non-empty string


@pytest.mark.asyncio
async def test_invalid_zip_returns_422(
    client: AsyncClient,
    live_campaign: Campaign,
) -> None:
    """Non-5-digit ZIP → 422."""
    for bad_zip in ["1234", "abcde", "123456"]:
        resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip={bad_zip}")
        assert resp.status_code == 422, f"Expected 422 for zip={bad_zip!r}, got {resp.status_code}"


@pytest.mark.asyncio
async def test_rate_limit_returns_503_with_retry_after(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """429 from civic API → 503 with Retry-After header forwarded."""
    mock_response = httpx.Response(429, headers={"Retry-After": "30"})
    mock_lookup.side_effect = httpx.HTTPStatusError("rate limited", request=None, response=mock_response)
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["fallback"] == "manual_entry"
    assert resp.headers.get("retry-after") == "30"


@pytest.mark.asyncio
async def test_campaign_ceiling_is_a_multiple_of_the_per_ip_limit(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """Both buckets are checked: the caller's IP, and the campaign's wider ceiling."""
    from app.api.v1.reps import REPS_CAMPAIGN_MULTIPLIER
    from app.config import settings

    mock_lookup.return_value = _SAMPLE_REPS
    with patch("app.api.v1.reps.check_rate_limit", new_callable=AsyncMock) as limiter:
        resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")

    assert resp.status_code == 200, resp.text
    limits = {call.args[1]: call.args[3] for call in limiter.await_args_list}
    assert limits["reps"] == settings.REPS_RATE_LIMIT
    assert limits["reps-campaign"] == settings.REPS_RATE_LIMIT * REPS_CAMPAIGN_MULTIPLIER


@pytest.mark.asyncio
async def test_missing_api_key_returns_503_with_fallback(
    client: AsyncClient,
    live_campaign: Campaign,
    mock_lookup: AsyncMock,
) -> None:
    """Missing API key surfaces as 503 with fallback: manual_entry (not 500)."""
    mock_lookup.side_effect = MissingApiKeyError("GOOGLE_CIVIC_API_KEY is not set")
    resp = await client.get(f"/api/v1/campaigns/{live_campaign.id}/reps?zip=90210")
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["fallback"] == "manual_entry"
