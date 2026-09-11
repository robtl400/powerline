"""Tests for the Redis sliding-window rate limiter.

Covers the count-before-admit contract (a rejected attempt is not recorded),
the default-limit fallback, window eviction, the shared bucket for callers with
no identifier, and atomicity under concurrent attempts.
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.rate_limiter import check_rate_limit, rate_key

SCOPE = "test-rate-limiter"


def test_rate_key_namespaces_scope_and_identifier():
    assert rate_key("auth", "user@test.example") == "rate:auth:user@test.example"


@pytest.fixture
def identifier() -> str:
    """A bucket identifier unique to one test."""
    return f"id-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
async def clear_buckets(redis):
    """Drop the shared "unknown" bucket this module uses, before and after."""
    key = f"rate:{SCOPE}:unknown"
    await redis.delete(key)
    yield
    await redis.delete(key)


async def test_rejects_at_limit_without_recording(redis, identifier):
    key = f"rate:{SCOPE}:{identifier}"

    for _ in range(3):
        await check_rate_limit(redis, SCOPE, identifier, 3)

    assert await redis.zcard(key) == 3

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit(redis, SCOPE, identifier, 3)

    assert exc.value.status_code == 429
    assert exc.value.detail == "Too many requests. Please try again later."
    assert await redis.zcard(key) == 3

    await redis.delete(key)


@pytest.mark.parametrize("limit", [None, 0, -1])
async def test_falls_back_to_default_limit(redis, identifier, limit):
    key = f"rate:{SCOPE}:{identifier}-{limit}"
    bucket = f"{identifier}-{limit}"
    await redis.delete(key)

    for _ in range(settings.DEFAULT_RATE_LIMIT):
        await check_rate_limit(redis, SCOPE, bucket, limit)

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit(redis, SCOPE, bucket, limit)

    assert exc.value.status_code == 429
    assert await redis.zcard(key) == settings.DEFAULT_RATE_LIMIT

    await redis.delete(key)


async def test_evicts_entries_older_than_window(redis, identifier):
    key = f"rate:{SCOPE}:{identifier}"
    now = time.time()
    await redis.zadd(key, {f"old-{i}": now - 120 for i in range(5)})

    await check_rate_limit(redis, SCOPE, identifier, 3, window_seconds=60)

    assert await redis.zcard(key) == 1

    await redis.delete(key)


async def test_empty_identifier_uses_unknown_bucket(redis):
    key = f"rate:{SCOPE}:unknown"

    for _ in range(2):
        await check_rate_limit(redis, SCOPE, "", 2)

    assert await redis.zcard(key) == 2

    with pytest.raises(HTTPException) as exc:
        await check_rate_limit(redis, SCOPE, "", 2)

    assert exc.value.status_code == 429
    assert await redis.zcard(key) == 2


async def test_concurrent_attempts_admit_exactly_the_limit(redis, identifier):
    key = f"rate:{SCOPE}:{identifier}"

    results = await asyncio.gather(
        *(check_rate_limit(redis, SCOPE, identifier, 3) for _ in range(20)),
        return_exceptions=True,
    )

    admitted = [r for r in results if r is None]
    rejected = [r for r in results if isinstance(r, HTTPException)]

    assert len(admitted) == 3
    assert len(rejected) == 17
    assert all(r.status_code == 429 for r in rejected)
    assert await redis.zcard(key) == 3

    await redis.delete(key)
