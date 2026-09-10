"""Redis sliding-window rate limiter.

Algorithm (sorted set per scope + identifier):
  Key: rate:{scope}:{identifier}  (identifier = phone_hash, IP address, email, …)
  On each attempt:
    1. ZREMRANGEBYSCORE — remove entries older than the window
    2. ZCOUNT — count the entries remaining in the window
    3. Reject with HTTP 429 when the count already reaches the limit, without
       recording the attempt
    4. Otherwise ZADD the attempt (unique member, score = now) and EXPIRE the
       key so it is cleaned up automatically

A limit of None or <= 0 falls back to settings.DEFAULT_RATE_LIMIT; there is no
unlimited mode and no bypass.
"""
from __future__ import annotations

import time
import uuid

import structlog
from fastapi import HTTPException
from redis.asyncio import Redis

log = structlog.get_logger()


async def check_rate_limit(
    redis: Redis,
    scope: str,
    identifier: str,
    limit: int | None,
    window_seconds: int = 3600,
) -> None:
    """Raise HTTP 429 if the identifier has exceeded its limit within the window.

    Args:
        redis: Async Redis client from get_redis().
        scope: namespace for the counter, e.g. "call", "token", "auth", "reps".
        identifier: phone_hash, IP address, or other per-caller key.
        limit: max attempts per window; None or <= 0 uses settings.DEFAULT_RATE_LIMIT.
        window_seconds: sliding window length in seconds.
    """
    from app.config import settings

    if not identifier:
        log.warning("rate_limit_missing_identifier", scope=scope)
        return

    effective_limit = limit if limit and limit > 0 else settings.DEFAULT_RATE_LIMIT

    now = time.time()
    window_start = now - window_seconds
    key = f"rate:{scope}:{identifier}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zcount(key, window_start, "+inf")
    results = await pipe.execute()

    count: int = results[1]

    if count >= effective_limit:
        log.warning(
            "rate_limit_exceeded",
            scope=scope,
            identifier=identifier[:12],  # truncate for privacy in logs
            count=count,
            limit=effective_limit,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )

    pipe = redis.pipeline()
    pipe.zadd(key, {str(uuid.uuid4()): now})
    pipe.expire(key, window_seconds)
    await pipe.execute()
