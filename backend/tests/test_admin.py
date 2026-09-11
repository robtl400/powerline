"""Tests for the admin dashboard and blocklist endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.helpers import phone_hash
from app.config import settings
from app.models.call_session import CallSession
from app.models.campaign import Campaign

BLOCK_PHONE = "+12025550611"


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
    assert body["phone_hash"] == phone_hash(BLOCK_PHONE)
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
    page = listed.json()
    assert entry_id in [e["id"] for e in page["items"]]
    assert page["total"] >= len(page["items"])

    await _delete(client, entry_id, admin_headers)

    listed_again = await client.get("/api/v1/admin/blocklist", headers=admin_headers)
    assert entry_id not in [e["id"] for e in listed_again.json()["items"]]


async def test_blocklist_total_counts_past_the_page(
    client: AsyncClient, admin_headers: dict
) -> None:
    """`limit` bounds the items; `total` still counts every entry."""
    created = []
    for i in range(2):
        resp = await client.post(
            "/api/v1/admin/blocklist",
            json={"ip_address": f"203.0.113.{20 + i}", "reason": "paging"},
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        created.append(resp.json()["id"])

    try:
        page = await client.get("/api/v1/admin/blocklist?limit=1", headers=admin_headers)
        assert page.status_code == 200
        body = page.json()
        assert len(body["items"]) == 1
        assert body["total"] >= 2
    finally:
        for entry_id in created:
            await _delete(client, entry_id, admin_headers)


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


# ---------------------------------------------------------------------------
# Dashboard: calendar days follow the configured timezone
# ---------------------------------------------------------------------------


async def _daily_series(client: AsyncClient, admin_headers: dict) -> dict[str, int]:
    resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    return {row["date"]: row["count"] for row in resp.json()["calls_last_7_days"]}


async def test_dashboard_days_follow_configured_timezone(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    monkeypatch,
) -> None:
    """An 03:00 UTC session lands on the previous calendar day in Los Angeles."""
    monkeypatch.setattr(settings, "TIMEZONE", "America/Los_Angeles")

    stamp = (datetime.now(UTC) - timedelta(days=2)).replace(
        hour=3, minute=0, second=0, microsecond=0
    )
    utc_day = stamp.date()
    local_day = stamp.astimezone(ZoneInfo("America/Los_Angeles")).date()
    assert local_day == utc_day - timedelta(days=1)

    before = await _daily_series(client, admin_headers)

    session = CallSession(
        campaign_id=campaign.id,
        connection_type="webrtc",
        twilio_call_sid=f"CAtz{uuid.uuid4().hex[:20]}",
        status="completed",
        created_at=stamp,
    )
    db.add(session)
    await db.commit()

    after = await _daily_series(client, admin_headers)

    assert after[local_day.isoformat()] == before[local_day.isoformat()] + 1
    assert after[utc_day.isoformat()] == before[utc_day.isoformat()]

    await db.execute(delete(CallSession).where(CallSession.id == session.id))
    await db.commit()


# ---------------------------------------------------------------------------
# Dashboard: totals and the seven-day series
# ---------------------------------------------------------------------------


async def _dashboard(client: AsyncClient, headers: dict) -> dict:
    resp = await client.get("/api/v1/admin/dashboard", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_dashboard_counts_new_sessions_across_every_window(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    monkeypatch,
) -> None:
    """Three fresh sessions land in today, this week, this month, and the breakdown."""
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")

    before = await _dashboard(client, admin_headers)

    sessions = [
        CallSession(
            campaign_id=campaign.id,
            connection_type=connection_type,
            twilio_call_sid=f"CAdash{uuid.uuid4().hex[:20]}",
            status="completed",
        )
        for connection_type in ("webrtc", "outbound_phone", "inbound_phone")
    ]
    db.add_all(sessions)
    await db.commit()

    after = await _dashboard(client, admin_headers)

    assert after["calls_today"] == before["calls_today"] + 3
    assert after["calls_this_week"] == before["calls_this_week"] + 3
    assert after["calls_this_month"] == before["calls_this_month"] + 3
    assert after["webrtc_count"] == before["webrtc_count"] + 1
    assert after["phone_count"] == before["phone_count"] + 2
    assert after["calls_last_7_days"][-1]["count"] == (
        before["calls_last_7_days"][-1]["count"] + 3
    )

    await db.execute(delete(CallSession).where(CallSession.id.in_([s.id for s in sessions])))
    await db.commit()


async def test_dashboard_counts_live_campaigns(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
) -> None:
    before = await _dashboard(client, admin_headers)

    campaign.status = "live"
    await db.commit()

    after = await _dashboard(client, admin_headers)
    assert after["active_campaigns"] == before["active_campaigns"] + 1

    campaign.status = "draft"
    await db.commit()


async def test_dashboard_series_is_seven_zero_filled_days_oldest_first(
    client: AsyncClient, admin_headers: dict, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")

    series = (await _dashboard(client, admin_headers))["calls_last_7_days"]
    assert len(series) == 7

    days = [datetime.fromisoformat(row["date"]).date() for row in series]
    assert days == sorted(days)
    assert days[-1] == datetime.now(UTC).date()
    assert all(days[i + 1] - days[i] == timedelta(days=1) for i in range(6))
    assert all(isinstance(row["count"], int) for row in series)


async def test_dashboard_connection_split_stops_at_the_thirty_day_window(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    monkeypatch,
) -> None:
    """A session older than the month tile's window is outside the browser/phone split too."""
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")

    before = await _dashboard(client, admin_headers)

    stale = CallSession(
        campaign_id=campaign.id,
        connection_type="webrtc",
        twilio_call_sid=f"CAold{uuid.uuid4().hex[:20]}",
        status="completed",
        created_at=datetime.now(UTC) - timedelta(days=40),
    )
    db.add(stale)
    await db.commit()

    after = await _dashboard(client, admin_headers)

    assert after["webrtc_count"] == before["webrtc_count"]
    assert after["calls_this_month"] == before["calls_this_month"]

    await db.execute(delete(CallSession).where(CallSession.id == stale.id))
    await db.commit()
