"""Module-level async Redis client singleton.

A single connection pool is reused across all requests rather than
creating a new pool per request. Import get_redis() wherever Redis
access is needed (webhooks, auth, rate limiting, call state).
"""
from __future__ import annotations

from urllib.parse import urlsplit

import redis.asyncio as aioredis

_redis: aioredis.Redis | None = None


def connection_kwargs(url: str, password: str) -> dict:
    """Build client kwargs, ignoring REDIS_PASSWORD when the URL carries one."""
    kwargs: dict = {"decode_responses": True}
    if password and "@" not in urlsplit(url).netloc:
        kwargs["password"] = password
    return kwargs


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        from app.config import settings

        _redis = aioredis.from_url(
            settings.REDIS_URL,
            **connection_kwargs(settings.REDIS_URL, settings.REDIS_PASSWORD),
        )
    return _redis
