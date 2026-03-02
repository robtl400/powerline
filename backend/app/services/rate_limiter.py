"""Redis sliding-window rate limiter for call sessions.

Algorithm (sorted set per identifier):
  Key: rate:{identifier}  (identifier = phone_hash or IP address)
  On each attempt:
    1. ZREMRANGEBYSCORE — remove entries older than the window
    2. ZADD — record this attempt (score = member = current unix timestamp)
    3. ZCOUNT — count entries in the window
    4. EXPIRE — reset TTL so the key is cleaned up automatically
  Reject if count exceeds the campaign's rate_limit.

Admin bypass: pass is_admin=True to skip all checks.
"""
from __future__ import annotations

import time

import structlog
from fastapi import HTTPException
from redis.asyncio import Redis

log = structlog.get_logger()

_WINDOW_SECONDS = 3600  # 1-hour sliding window


async def check_rate_limit(
    redis: Redis,
    identifier: str,
    limit: int | None,
    is_admin: bool = False,
) -> None:
    """Raise HTTP 429 if the identifier has exceeded the hourly rate limit.

    Args:
        redis: Async Redis client from get_redis().
        identifier: phone_hash (phone path) or IP address (WebRTC path).
        limit: max calls per hour from campaign.rate_limit; None = unlimited.
        is_admin: if True, skip all rate limit checks (mirrors dev-bypass pattern).
    """
    if is_admin or limit is None or not identifier:
        return

    now = time.time()
    window_start = now - _WINDOW_SECONDS
    key = f"rate:{identifier}"

    # Pipeline for atomicity and reduced round-trips.
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", window_start)
    pipe.zadd(key, {str(now): now})
    pipe.zcount(key, window_start, "+inf")
    pipe.expire(key, _WINDOW_SECONDS)
    results = await pipe.execute()

    count: int = results[2]  # zcount result index

    if count > limit:
        log.warning(
            "rate_limit_exceeded",
            identifier=identifier[:12],  # truncate for privacy in logs
            count=count,
            limit=limit,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many calls. Please try again later.",
        )
