"""Phone number lookup service with Redis caching.

Validates caller phone numbers before connecting them to campaign targets.
Results are cached 24h to avoid repeated Twilio Lookup API charges.
"""
from __future__ import annotations

import asyncio
import json
import structlog
from fastapi import HTTPException
from redis.asyncio import Redis

from app.models.campaign import Campaign
from app.services.telephony.base import LookupResult, TelephonyProvider

log = structlog.get_logger()

LOOKUP_CACHE_TTL = 86400  # 24 hours


class LookupService:
    def __init__(self, provider: TelephonyProvider, redis_client: Redis) -> None:
        self._provider = provider
        self._redis = redis_client

    async def validate_number(self, phone: str, campaign: Campaign) -> LookupResult:
        """Validate a caller's phone number, enforcing campaign-level restrictions.

        Raises HTTPException(422) if campaign requires mobile and number isn't mobile.
        Raises HTTPException(503) if the Lookup API is unavailable.
        """
        cache_key = f"lookup:{phone}"

        cached = await self._redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            result = LookupResult(
                phone=data["phone"],
                is_valid=data["is_valid"],
                line_type=data["line_type"],
                raw=data["raw"],
            )
            log.debug("lookup_cache_hit", phone=phone)
        else:
            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    None, self._provider.validate_phone, phone
                )
            except Exception as exc:
                log.warning("lookup_api_error", phone=phone, error=str(exc))
                raise HTTPException(
                    status_code=503,
                    detail="Phone validation service temporarily unavailable",
                )

            await self._redis.setex(
                cache_key,
                LOOKUP_CACHE_TTL,
                json.dumps({
                    "phone": result.phone,
                    "is_valid": result.is_valid,
                    "line_type": result.line_type,
                    "raw": result.raw,
                }),
            )
            log.debug("lookup_cache_miss", phone=phone, line_type=result.line_type)

        # Twilio Lookup returns line_type values like "mobile", "landline", "voip",
        # "nonFixedVoip", "tollFree" — only "mobile" passes the mobile-required check.
        if campaign.lookup_require_mobile and result.line_type != "mobile":
            raise HTTPException(
                status_code=422,
                detail="A mobile phone number is required to participate in this campaign.",
            )

        return result
