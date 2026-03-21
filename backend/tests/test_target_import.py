"""Tests for the CSV target import endpoint."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.models.user import User


def _csv_file(content: str, filename: str = "targets.csv", ct: str = "text/csv") -> dict:
    return {"file": (filename, content.encode(), ct)}


VALID_CSV = """\
name,title,phone_number,location
Rep Smith,Representative,+12025551001,CA-12
Sen Jones,Senator,+12025551002,WA
Rep Doe,Representative,+12025551003,NY-10
"""

PARTIAL_CSV = """\
name,title,phone_number,location
Rep Smith,Representative,+12025551001,CA-12
Rep Bad,Representative,555-bad-phone,CA-13
Rep Doe,Representative,+12025551003,NY-10
"""

UPSERT_CSV_FIRST = """\
name,title,phone_number,location,external_id
Original Name,Representative,+12025551001,CA-12,rep-001
"""

UPSERT_CSV_SECOND = """\
name,title,phone_number,location,external_id
Updated Name,Representative,+12025551002,CA-13,rep-001
"""


async def test_import_happy_path(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(VALID_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 3
    assert data["updated"] == 0
    assert data["errors"] == []

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    assert len(ct_result.scalars().all()) == 3


async def test_import_partial_success(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(PARTIAL_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row"] == 3  # second data row (row 3 including header)

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    assert len(ct_result.scalars().all()) == 2


async def test_import_upsert(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    # First import — inserts 1 target with external_id=rep-001
    resp1 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(UPSERT_CSV_FIRST),
        headers=admin_headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["imported"] == 1
    assert resp1.json()["updated"] == 0

    # Second import — same external_id should update, not insert
    resp2 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(UPSERT_CSV_SECOND),
        headers=admin_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["imported"] == 0
    assert resp2.json()["updated"] == 1
    assert resp2.json()["errors"] == []

    # Only 1 target should exist in the campaign
    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    cts = ct_result.scalars().all()
    assert len(cts) == 1

    # The target's name should be updated
    t_result = await db.execute(select(Target).where(Target.id == cts[0].target_id))
    target = t_result.scalar_one()
    assert target.name == "Updated Name"


async def test_import_empty_file(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(""),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_import_too_large(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    # 6 MB of data exceeds the 5 MB limit
    large_content = "x" * (6 * 1024 * 1024)
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(large_content),
        headers=admin_headers,
    )
    assert resp.status_code == 413


async def test_import_non_csv(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file("fake image data", filename="photo.png", ct="image/png"),
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_import_missing_required_columns(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """CSV missing the 'location' column should be rejected with 400."""
    csv_no_location = "name,title,phone_number\nRep Smith,Representative,+12025551001\n"
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(csv_no_location),
        headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "location" in resp.json()["detail"]


async def test_import_non_utf8_encoding(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """Non-UTF-8 encoded files should be rejected with 400."""
    latin1_bytes = "name,title,phone_number,location\nRép,Senator,+12025551001,CA\n".encode("latin-1")
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files={"file": ("targets.csv", latin1_bytes, "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_import_requires_auth(
    client: AsyncClient, campaign: Campaign
) -> None:
    """Import endpoint must reject unauthenticated requests."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(VALID_CSV),
    )
    assert resp.status_code in (401, 403)


async def test_import_errors_download(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """After a partial import, the error download endpoint returns a CSV."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(PARTIAL_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["errors"]

    dl = await client.get(
        f"/api/v1/campaigns/{campaign.id}/targets/import-errors",
        headers=admin_headers,
    )
    assert dl.status_code == 200
    assert "text/csv" in dl.headers["content-type"]
    text = dl.text
    assert "row" in text
    assert "error_reason" in text


async def test_import_errors_download_no_prior_import(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """Requesting import errors when none exist returns 404."""
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/targets/import-errors",
        headers=admin_headers,
    )
    assert resp.status_code == 404
