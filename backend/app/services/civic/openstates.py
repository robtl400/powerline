from __future__ import annotations

import csv
import pathlib

import httpx
import structlog

from app.config import settings
from app.services.civic.base import RepInfo
from app.services.civic.google_civic import MissingApiKeyError

log = structlog.get_logger()

_DATA_DIR = pathlib.Path(__file__).parent / "data"
_ZIPS_CSV = _DATA_DIR / "uszips.csv"
_BASE = "https://v3.openstates.org"


def _load_zip_centroids() -> dict[str, tuple[float, float]]:
    centroids: dict[str, tuple[float, float]] = {}
    try:
        with open(_ZIPS_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                z = str(row["zip"]).zfill(5)
                try:
                    centroids[z] = (float(row["lat"]), float(row["lng"]))
                except (ValueError, KeyError):
                    pass
    except FileNotFoundError:
        log.warning("uszips_csv_missing", path=str(_ZIPS_CSV))
    return centroids


# Loaded once at import time — ~3 MB, negligible memory, avoids per-request I/O.
_CENTROIDS = _load_zip_centroids()


async def fetch_state_reps(zip_code: str) -> list[RepInfo]:
    if not settings.OPENSTATES_API_KEY:
        raise MissingApiKeyError("OPENSTATES_API_KEY is not set")

    centroid = _CENTROIDS.get(zip_code.zfill(5))
    if not centroid:
        log.warning("unknown_zip_centroid", zip=zip_code)
        return []

    lat, lng = centroid
    async with httpx.AsyncClient(
        base_url=_BASE,
        headers={"X-API-KEY": settings.OPENSTATES_API_KEY},
        timeout=10.0,
    ) as client:
        resp = await client.get("/api/v3/people.geo", params={"lat": lat, "lng": lng})
        resp.raise_for_status()

    results: list[RepInfo] = []
    for person in resp.json().get("results", []):
        phone = next(
            (c["value"] for c in person.get("contact_details", []) if c.get("type") == "voice"),
            None,
        )
        if not phone:
            continue
        results.append(RepInfo(
            name=person.get("name", ""),
            title=_format_title(person),
            phone=phone,
            level="state",
        ))

    return results


def _format_title(person: dict) -> str:
    role = person.get("current_role") or {}
    title = role.get("title", "")
    org = role.get("org_classification", "")
    if title and org:
        return f"{title}, {org}"
    return title or org or "State Legislator"
