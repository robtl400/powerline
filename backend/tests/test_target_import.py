"""Tests for the CSV target import endpoint."""

import csv
import io
import json
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.models.user import User
from app.schemas.target import ImportResult


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

RAGGED_CSV = """\
name,title,phone_number,location
Rep Smith,Representative,+12025551001,CA-12
Rep Ragged,Representative,+12025551004,CA-14,extra,columns
Rep Doe,Representative,+12025551003,NY-10
"""

FORMULA_PHONE_CSV = """\
name,title,phone_number,location
Rep Evil,Representative,"=HYPERLINK(""http://evil.example"",""click here"")",CA-12
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


async def test_import_ragged_row_is_a_row_error(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    """A row with more cells than the header fails that row only."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(RAGGED_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row"] == 3
    assert data["errors"][0]["error"] == "row has more columns than the header"

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


async def test_import_errors_download_neutralizes_formula_cells(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """A rejected cell that a spreadsheet would evaluate comes back as inert text."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(FORMULA_PHONE_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["errors"]

    dl = await client.get(
        f"/api/v1/campaigns/{campaign.id}/targets/import-errors",
        headers=admin_headers,
    )
    assert dl.status_code == 200
    rows = list(csv.reader(io.StringIO(dl.text)))
    assert len(rows) >= 2
    for row in rows:
        for cell in row:
            assert cell[:1] not in ("=", "+", "-", "@", "\t", "\r"), cell
    assert "'=HYPERLINK" in dl.text


async def test_import_errors_download_quotes_a_leading_formula_character(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, redis
) -> None:
    """Whatever reaches the cache, the exported cell never starts a formula."""
    await redis.set(
        f"import_errors:{campaign.id}",
        json.dumps([{"row": 2, "error": '=cmd|"/C calc"!A0'}]),
        ex=60,
    )

    dl = await client.get(
        f"/api/v1/campaigns/{campaign.id}/targets/import-errors",
        headers=admin_headers,
    )
    assert dl.status_code == 200
    rows = list(csv.reader(io.StringIO(dl.text)))
    assert rows[1][1] == '\'=cmd|"/C calc"!A0'

    await redis.delete(f"import_errors:{campaign.id}")


async def test_import_errors_download_no_prior_import(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """Requesting import errors when none exist returns 404."""
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/targets/import-errors",
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_import_lock_release_leaves_a_foreign_lock_alone(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, redis
) -> None:
    """A finishing import only deletes the lock it still owns."""
    lock_key = f"import_lock:{campaign.id}"

    async def _steal_lock(*args, **kwargs) -> ImportResult:
        await redis.set(lock_key, "another-request", ex=300)
        return ImportResult(imported=0, updated=0, errors=[])

    with patch("app.api.v1.campaigns._do_import", side_effect=_steal_lock):
        resp = await client.post(
            f"/api/v1/campaigns/{campaign.id}/targets/import",
            files=_csv_file(VALID_CSV),
            headers=admin_headers,
        )
    assert resp.status_code == 200
    assert await redis.get(lock_key) == "another-request"

    await redis.delete(lock_key)


async def test_import_lock_is_released_when_still_owned(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, redis
) -> None:
    lock_key = f"import_lock:{campaign.id}"
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(VALID_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert await redis.get(lock_key) is None


DUPLICATE_EXTERNAL_ID_CSV = """\
name,title,phone_number,location,external_id
First Row,Representative,+12025551001,CA-12,rep-001
Second Row,Senator,+12025551002,CA-13,rep-001
"""


async def test_import_collapses_a_repeated_external_id_within_one_file(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    """Two rows sharing an external_id produce one target; the later row wins."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(DUPLICATE_EXTERNAL_ID_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 1
    assert data["updated"] == 1
    assert data["errors"] == []

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    cts = ct_result.scalars().all()
    assert len(cts) == 1

    t_result = await db.execute(select(Target).where(Target.id == cts[0].target_id))
    target = t_result.scalar_one()
    assert target.name == "Second Row"
    assert target.title == "Senator"
    assert target.location == "CA-13"
    assert target.phone_number == "+12025551002"


async def test_import_over_long_cell_fails_only_that_row(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    """A cell wider than its column is a row error, not a failed import."""
    over_long_name = "N" * 201
    csv_content = (
        "name,title,phone_number,location\n"
        "Rep Smith,Representative,+12025551001,CA-12\n"
        f"{over_long_name},Representative,+12025551002,CA-13\n"
        "Rep Doe,Representative,+12025551003,NY-10\n"
    )

    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(csv_content),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row"] == 3
    assert data["errors"][0]["error"] == "name exceeds 200 characters"

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    assert len(ct_result.scalars().all()) == 2


PREMIUM_RATE_CSV = """\
name,title,phone_number,location
Rep Smith,Representative,+12025551001,CA-12
Pay Per Call,Representative,1-900-555-0100,CA-13
Rep Doe,Representative,+12025551003,NY-10
"""


async def test_import_premium_rate_row_is_a_row_error(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    """A 1-900 line fails its own row; the rest of the file still imports."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(PREMIUM_RATE_CSV),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["updated"] == 0
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row"] == 3
    assert "Premium-rate numbers are not supported" in data["errors"][0]["error"]

    ct_result = await db.execute(
        select(CampaignTarget).where(CampaignTarget.campaign_id == campaign.id)
    )
    assert len(ct_result.scalars().all()) == 2


async def test_add_target_rejects_a_premium_rate_number(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Pay Per Call",
            "title": "Representative",
            "phone_number": "+19005550100",
            "location": "CA-13",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "Premium-rate numbers are not supported" in resp.text


async def test_add_target_rejects_a_976_number(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Pay Per Call",
            "title": "Representative",
            "phone_number": "+19765550100",
            "location": "CA-13",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Rows go in as batched statements, and the lock survives a long import
# ---------------------------------------------------------------------------


def _bulk_csv(rows: int) -> str:
    lines = ["name,title,phone_number,location,external_id"]
    for i in range(rows):
        lines.append(f"Rep {i},Representative,+1202555{6000 + i:04d},CA-{i:02d},bulk-{i:04d}")
    return "\n".join(lines) + "\n"


async def test_import_writes_rows_in_batches(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file longer than one batch still lands as one contiguous, ordered block."""
    from app.api.v1 import campaigns as campaigns_module

    monkeypatch.setattr(campaigns_module, "_IMPORT_BATCH_ROWS", 2)

    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(_bulk_csv(5)),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 5

    rows = await db.execute(
        select(Target.external_id, CampaignTarget.order)
        .join(CampaignTarget, CampaignTarget.target_id == Target.id)
        .where(CampaignTarget.campaign_id == campaign.id)
        .order_by(CampaignTarget.order)
    )
    listed = rows.all()
    assert [order for _, order in listed] == [0, 1, 2, 3, 4]
    assert [external_id for external_id, _ in listed] == [f"bulk-{i:04d}" for i in range(5)]


async def test_import_extends_its_lock_while_the_rows_go_in(
    client: AsyncClient,
    campaign: Campaign,
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lock TTL is a window per batch, not a bet on how long the file takes."""
    from app.api.v1 import campaigns as campaigns_module

    refreshed: list[tuple[str, int]] = []
    real_refresh = campaigns_module.refresh_async

    async def _record(client_, key: str, token: str, ttl: int) -> bool:
        refreshed.append((key, ttl))
        return await real_refresh(client_, key, token, ttl)

    monkeypatch.setattr(campaigns_module, "_IMPORT_BATCH_ROWS", 2)
    monkeypatch.setattr(campaigns_module, "refresh_async", _record)

    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets/import",
        files=_csv_file(_bulk_csv(5)),
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    assert refreshed
    assert all(key == f"import_lock:{campaign.id}" for key, _ in refreshed)
    assert {ttl for _, ttl in refreshed} == {campaigns_module._IMPORT_LOCK_TTL_SECONDS}
