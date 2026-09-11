from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

import structlog

from app.services.civic.base import RepInfo
from app.services.civic.google_civic import MissingApiKeyError, fetch_federal_reps
from app.services.civic.openstates import fetch_state_reps

log = structlog.get_logger()

_PROVIDER_MAP: dict[str, Callable[[str], Awaitable[list[RepInfo]]]] = {
    "federal": fetch_federal_reps,
    "state": fetch_state_reps,
}


async def lookup(zip_code: str, embed_config: dict) -> list[RepInfo]:
    """
    Fan out to the providers indicated by embed_config["target_levels"].

    Resilience:
    - MissingApiKeyError from any provider → re-raised (caller returns 503)
    - Any other provider exception → logged, partial results returned
    """
    levels: list[str] = embed_config.get("target_levels", ["federal"])
    active = {lvl: _PROVIDER_MAP[lvl] for lvl in levels if lvl in _PROVIDER_MAP}

    if not active:
        return []

    settled = await asyncio.gather(
        *[fn(zip_code) for fn in active.values()],
        return_exceptions=True,
    )

    results: list[RepInfo] = []
    for level, outcome in zip(active.keys(), settled):
        if isinstance(outcome, MissingApiKeyError):
            raise outcome
        elif isinstance(outcome, BaseException):
            log.error("civic_provider_error", level=level, error=str(outcome))
        else:
            results.extend(outcome)

    return results
