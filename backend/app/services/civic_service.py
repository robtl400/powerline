from __future__ import annotations

import dataclasses
import json

import structlog

from app.redis_client import get_redis
from app.services.civic.google_civic import MissingApiKeyError
from app.services.civic.router import LevelRouter

log = structlog.get_logger()

REPS_CACHE_TTL = 86400  # 24 hours

_router = LevelRouter()


async def lookup_reps(zip_code: str, campaign_id: str, embed_config: dict) -> list[dict]:
    """
    Cache-first representative lookup.

    Returns a list of dicts with keys: name, title, phone, level.

    Raises:
        MissingApiKeyError: propagated from providers → endpoint maps to 503
        httpx.HTTPStatusError: 429 propagated → endpoint maps to 503 + Retry-After
        Exception: any other API failure → endpoint maps to 503
    """
    redis = get_redis()
    cache_key = f"reps:{zip_code}:{campaign_id}"

    cached = await redis.get(cache_key)
    if cached:
        log.debug("reps_cache_hit", zip=zip_code, campaign_id=campaign_id)
        return json.loads(cached)

    reps = await _router.lookup(zip_code, embed_config)
    payload = [dataclasses.asdict(r) for r in reps]

    try:
        await redis.set(cache_key, json.dumps(payload), ex=REPS_CACHE_TTL)
    except Exception as exc:
        log.warning("reps_cache_write_failed", zip=zip_code, campaign_id=campaign_id, error=str(exc))

    return payload
