from __future__ import annotations

import dataclasses
import json
import secrets

import structlog

from app.redis_client import get_redis
from app.services.civic.google_civic import MissingApiKeyError
from app.services.civic.router import LevelRouter

log = structlog.get_logger()

REPS_CACHE_TTL = 86400  # 24 hours
REP_TOKEN_TTL = 3600  # 1 hour — matches the widget's usable selection window

_router = LevelRouter()


def _configured_levels(embed_config: dict) -> list[str]:
    """The levels LevelRouter will actually fan out to, in a stable order."""
    return sorted(embed_config.get("target_levels", ["federal"]))


async def lookup_reps(zip_code: str, campaign_id: str, embed_config: dict) -> list[dict]:
    """
    Cache-first representative lookup.

    Returns a list of dicts with keys: name, title, phone, level.

    The configured levels are part of the cache key, so a campaign that changes
    target_levels reads a fresh lookup instead of the previous level set's reps.

    Raises:
        MissingApiKeyError: propagated from providers → endpoint maps to 503
        httpx.HTTPStatusError: 429 propagated → endpoint maps to 503 + Retry-After
        Exception: any other API failure → endpoint maps to 503
    """
    redis = get_redis()
    levels = "+".join(_configured_levels(embed_config))
    cache_key = f"reps:{zip_code}:{campaign_id}:{levels}"

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


async def issue_rep_tokens(campaign_id: str, reps: list[dict]) -> list[dict]:
    """Replace each rep's phone number with an opaque single-campaign handle.

    The phone number is stored server-side under `rep_token:{token}` and never
    reaches the client, so a caller can only dial numbers the lookup returned
    for the campaign they are calling on behalf of.

    Returns the reps with a `rep_token` key added and `phone` removed.
    """
    redis = get_redis()
    issued: list[dict] = []

    for rep in reps:
        token = secrets.token_urlsafe(24)
        record = {
            "campaign_id": campaign_id,
            "phone": rep.get("phone", ""),
            "name": rep.get("name", ""),
            "title": rep.get("title", ""),
            "level": rep.get("level", ""),
        }
        await redis.set(f"rep_token:{token}", json.dumps(record), ex=REP_TOKEN_TTL)

        public = {k: v for k, v in rep.items() if k != "phone"}
        public["rep_token"] = token
        issued.append(public)

    log.info("rep_tokens_issued", campaign_id=campaign_id, count=len(issued))
    return issued


async def resolve_rep_token(token: str, campaign_id: str) -> dict | None:
    """Return the stored rep record for a token, or None when it does not apply.

    A token resolves only for the campaign it was issued for. Tokens stay
    usable for the whole TTL so a retry after a failed call still works.
    """
    if not token:
        return None

    raw = await get_redis().get(f"rep_token:{token}")
    if not raw:
        return None

    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        log.warning("rep_token_corrupt", campaign_id=campaign_id)
        return None

    if record.get("campaign_id") != campaign_id:
        log.warning("rep_token_campaign_mismatch", campaign_id=campaign_id)
        return None

    return record
