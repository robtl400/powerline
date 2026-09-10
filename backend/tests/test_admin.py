"""Tests for the admin dashboard and blocklist endpoints."""
from __future__ import annotations

import hashlib

from httpx import AsyncClient

BLOCK_PHONE = "+12025550611"
BLOCK_PHONE_E164_HASH = hashlib.sha256(BLOCK_PHONE.encode()).hexdigest()


async def _delete(client: AsyncClient, entry_id: str, admin_headers: dict) -> None:
    resp = await client.delete(f"/api/v1/admin/blocklist/{entry_id}", headers=admin_headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Blocklist by phone number
# ---------------------------------------------------------------------------


async def test_create_by_phone_number_stores_matching_hash(
    client: AsyncClient, admin_headers: dict
) -> None:
    """A loosely formatted number is normalized, then hashed like the call paths."""
    resp = await client.post(
        "/api/v1/admin/blocklist",
        json={"phone_number": "+1 (202) 555-0611", "reason": "abuse"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["phone_hash"] == BLOCK_PHONE_E164_HASH
    assert body["ip_address"] is None
    assert body["reason"] == "abuse"

    await _delete(client, body["id"], admin_headers)


async def test_create_by_phone_number_rejects_junk(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/admin/blocklist",
        json={"phone_number": "not-a-phone"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_rejects_bad_phone_hash(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/admin/blocklist",
        json={"phone_hash": "deadbeef"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_rejects_bad_ip(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.post(
        "/api/v1/admin/blocklist",
        json={"ip_address": "999.1.1.1"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_create_requires_an_identifier(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/admin/blocklist",
        json={"reason": "no identifier"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_blocklist_list_and_delete_round_trip(
    client: AsyncClient, admin_headers: dict
) -> None:
    create = await client.post(
        "/api/v1/admin/blocklist",
        json={"ip_address": "203.0.113.7", "reason": "scripted calls"},
        headers=admin_headers,
    )
    assert create.status_code == 201, create.text
    entry_id = create.json()["id"]

    listed = await client.get("/api/v1/admin/blocklist", headers=admin_headers)
    assert listed.status_code == 200
    assert entry_id in [e["id"] for e in listed.json()]

    await _delete(client, entry_id, admin_headers)

    listed_again = await client.get("/api/v1/admin/blocklist", headers=admin_headers)
    assert entry_id not in [e["id"] for e in listed_again.json()]


async def test_delete_unknown_entry_is_404(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.delete(
        "/api/v1/admin/blocklist/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


async def test_staff_can_read_dashboard_and_blocklist(
    client: AsyncClient, staff_headers: dict
) -> None:
    dashboard = await client.get("/api/v1/admin/dashboard", headers=staff_headers)
    assert dashboard.status_code == 200

    blocklist = await client.get("/api/v1/admin/blocklist", headers=staff_headers)
    assert blocklist.status_code == 200


async def test_staff_cannot_write_blocklist(
    client: AsyncClient, admin_headers: dict, staff_headers: dict
) -> None:
    create = await client.post(
        "/api/v1/admin/blocklist",
        json={"ip_address": "203.0.113.8"},
        headers=staff_headers,
    )
    assert create.status_code == 403

    admin_create = await client.post(
        "/api/v1/admin/blocklist",
        json={"ip_address": "203.0.113.8"},
        headers=admin_headers,
    )
    assert admin_create.status_code == 201, admin_create.text
    entry_id = admin_create.json()["id"]

    staff_delete = await client.delete(
        f"/api/v1/admin/blocklist/{entry_id}", headers=staff_headers
    )
    assert staff_delete.status_code == 403

    await _delete(client, entry_id, admin_headers)


async def test_blocklist_requires_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/admin/blocklist")
    assert resp.status_code == 401
