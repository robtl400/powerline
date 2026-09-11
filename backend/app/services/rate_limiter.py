"""Redis sliding-window rate limiter.

Algorithm (sorted set per scope + identifier):
  Key: rate:{scope}:{identifier}  (identifier = phone_hash, IP address, email, …)
  Each attempt runs one Lua script so the read and the admission are a single
  atomic step — concurrent attempts cannot all observe the same pre-admission
  count. The script:
    1. ZREMRANGEBYSCORE — removes entries older than the window
    2. ZCARD — counts the entries remaining in the window
    3. Rejects with HTTP 429 when the count already reaches the limit, without
       recording the attempt
    4. Otherwise ZADDs the attempt (unique member, score = now) and EXPIREs the
       key so it is cleaned up automatically

A limit of None or <= 0 falls back to settings.DEFAULT_RATE_LIMIT; there is no
unlimited mode and no bypass. An empty identifier is limited too: those attempts
share the "unknown" bucket for the scope, so a caller cannot escape the limit by
withholding an identifier.
"""
from __future__ import annotations

import hashlib
import time
import uuid

import structlog
from fastapi import HTTPException
from redis.asyncio import Redis

log = structlog.get_logger()

_UNKNOWN_IDENTIFIER = "unknown"


def rate_key(scope: str, identifier: str) -> str:
    """Return the Redis key holding one scope's window for one identifier."""
    return f"rate:{scope}:{identifier}"

# Trims the window, then admits or rejects in the same atomic step. Returns
# {rejected, count}: on rejection the attempt is not recorded, so the count
# stays at the limit.
_ADMIT_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[3]) then
    return {1, count}
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[5])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return {0, count + 1}
"""


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
        identifier: phone_hash, IP address, or other per-caller key; an empty
            value is limited under the scope's shared "unknown" bucket.
        limit: max attempts per window; None or <= 0 uses settings.DEFAULT_RATE_LIMIT.
        window_seconds: sliding window length in seconds.
    """
    from app.config import settings

    if not identifier:
        log.warning("rate_limit_missing_identifier", scope=scope)
        identifier = _UNKNOWN_IDENTIFIER

    effective_limit = limit if limit and limit > 0 else settings.DEFAULT_RATE_LIMIT

    now = time.time()
    window_start = now - window_seconds
    key = rate_key(scope, identifier)

    rejected, count = await redis.eval(
        _ADMIT_LUA,
        1,
        key,
        window_start,
        now,
        effective_limit,
        window_seconds,
        str(uuid.uuid4()),
    )

    if rejected:
        log.warning(
            "rate_limit_exceeded",
            scope=scope,
            # An identifier may be a raw phone number, so only a digest is logged.
            identifier_digest=hashlib.sha256(identifier.encode()).hexdigest()[:12],
            count=count,
            limit=effective_limit,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
        )
