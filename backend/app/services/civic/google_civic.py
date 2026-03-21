from __future__ import annotations

import structlog
import httpx

from app.config import settings
from app.services.civic.base import RepInfo

log = structlog.get_logger()

_BASE = "https://www.googleapis.com/civicinfo/v2/representatives"


class MissingApiKeyError(Exception):
    """Raised when a required Civic API key is not configured."""


async def fetch_federal_reps(zip_code: str) -> list[RepInfo]:
    if not settings.GOOGLE_CIVIC_API_KEY:
        raise MissingApiKeyError("GOOGLE_CIVIC_API_KEY is not set")

    params = {
        "key": settings.GOOGLE_CIVIC_API_KEY,
        "address": zip_code,
        "levels": "country",
        "roles": ["legislatorUpperBody", "legislatorLowerBody"],
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(_BASE, params=params)
        resp.raise_for_status()  # propagates 429 as HTTPStatusError

    data = resp.json()
    officials: list[dict] = data.get("officials", [])
    offices: list[dict] = data.get("offices", [])

    results: list[RepInfo] = []
    for office in offices:
        title = office.get("name", "")
        for idx in office.get("officialIndices", []):
            if idx >= len(officials):
                continue
            official = officials[idx]
            phones: list[str] = official.get("phones", [])
            if not phones:
                log.debug("civic_no_phone", name=official.get("name"), title=title)
                continue
            results.append(RepInfo(
                name=official.get("name", ""),
                title=title,
                phone=phones[0],
                level="federal",
            ))

    return results
