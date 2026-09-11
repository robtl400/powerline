"""Smoke test: health endpoint responds correctly."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings
from app.main import app
from app.version import __version__


async def _health() -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_health() -> None:
    data = await _health()
    assert data["status"] == "ok"
    assert data["version"] == __version__


@pytest.mark.asyncio
async def test_health_publishes_the_default_rate_limit() -> None:
    """The campaign form reads the server default from here instead of hardcoding it."""
    data = await _health()
    assert data["default_rate_limit"] == settings.DEFAULT_RATE_LIMIT


@pytest.mark.asyncio
async def test_health_exposes_only_public_fields() -> None:
    data = await _health()
    assert set(data) == {"status", "version", "default_rate_limit"}
