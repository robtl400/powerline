"""Module-level async Redis client singleton.

A single connection pool is reused across all requests rather than
creating a new pool per request. Import get_redis() wherever Redis
access is needed (webhooks, lookup service, auth, etc.).
"""
from __future__ import annotations

import redis.asyncio as aioredis


_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        from app.config import settings

        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis
