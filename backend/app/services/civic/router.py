from __future__ import annotations

import asyncio
import dataclasses
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


@dataclasses.dataclass
class LookupResult:
    """What a fan-out produced, and which levels did not answer.

    `failures` maps a level to the exception its provider raised, in the order
    the levels were fanned out, so a caller can tell a complete answer from a
    partial one and re-raise a provider's own error.
    """

    reps: list[RepInfo]
    attempted_levels: tuple[str, ...]
    failures: dict[str, BaseException]

    @property
    def failed_levels(self) -> set[str]:
        return set(self.failures)

    @property
    def all_levels_failed(self) -> bool:
        return bool(self.attempted_levels) and len(self.failures) == len(self.attempted_levels)

    @property
    def last_failure(self) -> BaseException | None:
        return next(reversed(list(self.failures.values())), None)


async def lookup(zip_code: str, embed_config: dict) -> LookupResult:
    """
    Fan out to the providers indicated by embed_config["target_levels"].

    Resilience:
    - MissingApiKeyError from any provider → re-raised (caller returns 503)
    - Any other provider exception → logged and recorded in the result's
      `failures`, alongside whatever the surviving levels returned
    """
    levels: list[str] = embed_config.get("target_levels", ["federal"])
    active = {lvl: _PROVIDER_MAP[lvl] for lvl in levels if lvl in _PROVIDER_MAP}

    if not active:
        return LookupResult(reps=[], attempted_levels=(), failures={})

    settled = await asyncio.gather(
        *[fn(zip_code) for fn in active.values()],
        return_exceptions=True,
    )

    results: list[RepInfo] = []
    failures: dict[str, BaseException] = {}
    for level, outcome in zip(active.keys(), settled):
        if isinstance(outcome, MissingApiKeyError):
            raise outcome
        elif isinstance(outcome, BaseException):
            log.error("civic_provider_error", level=level, error=str(outcome))
            failures[level] = outcome
        else:
            results.extend(outcome)

    return LookupResult(
        reps=results,
        attempted_levels=tuple(active.keys()),
        failures=failures,
    )
