"""Tests for the campaign analytics endpoints and their filter validation."""
from __future__ import annotations

import csv
import io
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import analytics
from app.config import settings
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target

_ROUTES = ["calls", "calls/export"]

# A fixed past instant keeps the date-range assertions independent of "today".
SEEDED_AT = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
IN_RANGE = "start=2024-06-01&end=2024-06-30"
OUT_OF_RANGE = "start=2024-07-01&end=2024-07-31"


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("query", [
    "status=retired",
    "status=busy",
    "connection_type=carrier_pigeon",
    "connection_type=webrtc_v2",
])
async def test_bad_filter_values_are_rejected(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, route: str, query: str
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/{route}?{query}", headers=admin_headers
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("route", _ROUTES)
@pytest.mark.parametrize("query", [
    "status=completed",
    "status=in_progress",
    "connection_type=webrtc",
    "connection_type=inbound_phone",
])
async def test_valid_filter_values_are_accepted(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, route: str, query: str
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/{route}?{query}", headers=admin_headers
    )
    assert resp.status_code == 200


async def test_unknown_campaign_still_404s(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{uuid.uuid4()}/calls?status=completed", headers=admin_headers
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Seeded campaign: 3 sessions (2 completed, 1 failed) and 5 calls
# ---------------------------------------------------------------------------


@pytest.fixture
async def seeded(
    db: AsyncSession, campaign: Campaign, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[tuple[Campaign, Target, Target], None]:
    """One campaign with a known, fully deterministic call history."""
    monkeypatch.setattr(settings, "TIMEZONE", "UTC")

    first = Target(
        name="Sen. First", title="Senator", phone_number="+12025556001", location="WA"
    )
    second = Target(
        name="Rep. Second",
        title="Representative",
        phone_number="+12025556002",
        location="WA-07",
    )
    db.add_all([first, second])
    await db.flush()
    db.add_all([
        CampaignTarget(campaign_id=campaign.id, target_id=first.id, order=0),
        CampaignTarget(campaign_id=campaign.id, target_id=second.id, order=1),
    ])

    def _session(connection_type: str, status: str, duration: int | None) -> CallSession:
        return CallSession(
            campaign_id=campaign.id,
            connection_type=connection_type,
            twilio_call_sid=f"CAan{uuid.uuid4().hex[:20]}",
            status=status,
            duration=duration,
            created_at=SEEDED_AT,
        )

    done_webrtc = _session("webrtc", "completed", 100)
    done_phone = _session("outbound_phone", "completed", 200)
    dropped = _session("webrtc", "failed", None)
    db.add_all([done_webrtc, done_phone, dropped])
    await db.flush()

    def _call(
        session: CallSession,
        target: Target,
        status: str,
        duration: int,
        quality: float | None,
    ) -> Call:
        return Call(
            session_id=session.id,
            campaign_id=campaign.id,
            target_id=target.id,
            twilio_call_sid=f"CAleg{uuid.uuid4().hex[:20]}",
            status=status,
            duration=duration,
            quality_score=quality,
            created_at=SEEDED_AT,
        )

    db.add_all([
        _call(done_webrtc, first, "completed", 30, 4.0),
        _call(done_webrtc, second, "completed", 50, 5.0),
        _call(done_phone, first, "completed", 70, None),
        _call(dropped, first, "failed", 0, None),
        _call(dropped, second, "busy", 0, None),
    ])
    await db.commit()

    session_ids = [done_webrtc.id, done_phone.id, dropped.id]
    target_ids = [first.id, second.id]

    yield campaign, first, second

    await db.execute(delete(Call).where(Call.session_id.in_(session_ids)))
    await db.execute(delete(CallSession).where(CallSession.id.in_(session_ids)))
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id.in_(target_ids)))
    await db.commit()
    await db.execute(delete(Target).where(Target.id.in_(target_ids)))
    await db.commit()


# ---------------------------------------------------------------------------
# GET /{id}/stats
# ---------------------------------------------------------------------------


async def test_stats_totals_and_breakdowns(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, first, second = seeded

    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/stats", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_sessions"] == 3
    assert body["completed_sessions"] == 2
    assert body["completion_rate"] == 0.6667
    assert body["avg_calls_per_session"] == 1.67
    assert body["connection_type_breakdown"] == {"webrtc": 2, "outbound_phone": 1}

    # Ordered by call volume descending: the first target took three calls.
    per_target = body["per_target"]
    assert [row["target_id"] for row in per_target] == [str(first.id), str(second.id)]
    assert per_target[0]["total_calls"] == 3
    assert per_target[0]["completed_calls"] == 2
    assert per_target[0]["avg_duration_seconds"] == pytest.approx(100 / 3)
    assert per_target[1]["total_calls"] == 2
    assert per_target[1]["completed_calls"] == 1
    assert per_target[1]["avg_duration_seconds"] == pytest.approx(25.0)


async def test_stats_on_an_empty_campaign_is_all_zeros(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """No sessions means no division by zero anywhere in the aggregate."""
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/stats", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "total_sessions": 0,
        "completed_sessions": 0,
        "completion_rate": 0.0,
        "avg_calls_per_session": 0.0,
        "connection_type_breakdown": {},
        "per_target": [],
    }


# ---------------------------------------------------------------------------
# GET /{id}/calls
# ---------------------------------------------------------------------------


async def test_calls_returns_every_session_with_its_call_count(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/calls", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert sorted(row["call_count"] for row in body["items"]) == [1, 2, 2]


async def test_calls_pagination_keeps_the_unpaged_total(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    page = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls?skip=0&limit=2", headers=admin_headers
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2

    tail = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls?skip=2&limit=2", headers=admin_headers
    )
    assert tail.status_code == 200
    assert len(tail.json()["items"]) == 1

    page_ids = {row["id"] for row in page.json()["items"]}
    assert page_ids.isdisjoint({row["id"] for row in tail.json()["items"]})


@pytest.mark.parametrize("query,expected", [
    ("status=completed", 2),
    ("status=failed", 1),
    ("status=initiated", 0),
    ("connection_type=webrtc", 2),
    ("connection_type=outbound_phone", 1),
    ("connection_type=inbound_phone", 0),
    ("status=completed&connection_type=webrtc", 1),
    (IN_RANGE, 3),
    (OUT_OF_RANGE, 0),
    ("start=2024-06-16", 0),
    ("end=2024-06-14", 0),
])
async def test_calls_filters(
    client: AsyncClient,
    seeded: tuple[Campaign, Target, Target],
    admin_headers: dict,
    query: str,
    expected: int,
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls?{query}", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == expected


async def test_calls_on_an_empty_campaign_is_an_empty_page(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/calls", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "items": []}


@pytest.mark.parametrize("route", ["calls", "calls/export", "calls-by-date"])
async def test_invalid_start_date_is_422(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, route: str
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/{route}?start=last-tuesday", headers=admin_headers
    )
    assert resp.status_code == 422
    assert "Invalid date format" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{id}/calls/export
# ---------------------------------------------------------------------------


async def test_export_writes_a_header_and_one_row_per_session(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["content-disposition"] == (
        f'attachment; filename="calls-{campaign.id}.csv"'
    )

    lines = resp.text.strip().splitlines()
    assert lines[0] == (
        "id,created_at,connection_type,status,call_count,duration_seconds"
    )
    assert len(lines) == 4


async def test_export_honours_the_same_filters_as_calls(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    filtered = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export?status=completed",
        headers=admin_headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.text.strip().splitlines()) == 3

    empty = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export?{OUT_OF_RANGE}", headers=admin_headers
    )
    assert empty.status_code == 200
    assert len(empty.text.strip().splitlines()) == 1


async def test_export_on_an_empty_campaign_is_a_header_only(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export", headers=admin_headers
    )
    assert resp.status_code == 200
    assert len(resp.text.strip().splitlines()) == 1


async def test_export_row_contents_match_the_seeded_sessions(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    # The three sessions share one created_at, so their order is not pinned.
    assert {
        (r["connection_type"], r["status"], r["call_count"], r["duration_seconds"])
        for r in rows
    } == {
        ("webrtc", "completed", "2", "100"),
        ("outbound_phone", "completed", "1", "200"),
        ("webrtc", "failed", "2", ""),
    }
    assert all(r["created_at"] == SEEDED_AT.isoformat() for r in rows)
    assert all(uuid.UUID(r["id"]) for r in rows)


async def test_export_stops_at_the_row_cap_and_says_so(
    client: AsyncClient,
    seeded: tuple[Campaign, Target, Target],
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _, _ = seeded
    monkeypatch.setattr(analytics, "MAX_EXPORT_ROWS", 2)

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text

    lines = resp.text.strip().splitlines()
    assert len(lines) == 4
    assert lines[-1] == "# truncated: export is limited to 2 rows"

    rows = list(csv.DictReader(io.StringIO("\n".join(lines[:-1]))))
    assert len(rows) == 2


async def test_export_under_the_cap_has_no_truncation_line(
    client: AsyncClient,
    seeded: tuple[Campaign, Target, Target],
    admin_headers: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign, _, _ = seeded
    monkeypatch.setattr(analytics, "MAX_EXPORT_ROWS", 3)

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls/export", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    assert "# truncated" not in resp.text
    assert len(resp.text.strip().splitlines()) == 4


# ---------------------------------------------------------------------------
# GET /{id}/calls-by-date
# ---------------------------------------------------------------------------


async def test_calls_by_date_groups_by_day(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls-by-date?{IN_RANGE}&granularity=day",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == [{"date": "2024-06-15", "count": 3}]


async def test_calls_by_date_groups_by_week(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    """Postgres truncates to the Monday of the week the sessions landed in."""
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls-by-date?{IN_RANGE}&granularity=week",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["date"].startswith("2024-06-10")
    assert rows[0]["count"] == 3


async def test_calls_by_date_outside_the_range_is_empty(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls-by-date?{OUT_OF_RANGE}", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json() == []


async def test_calls_by_date_rejects_an_unknown_granularity(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/calls-by-date?granularity=fortnight",
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /{id}/quality
# ---------------------------------------------------------------------------


async def test_quality_scores_failures_and_connection_rate(
    client: AsyncClient, seeded: tuple[Campaign, Target, Target], admin_headers: dict
) -> None:
    campaign, _, _ = seeded

    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/quality", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "total_calls": 5,
        "calls_with_quality": 2,
        "avg_quality_score": 4.5,
        "connection_rate": 0.6667,
        "failure_breakdown": {"failed": 1, "busy": 1},
    }


async def test_quality_on_an_empty_campaign_is_all_zeros(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/quality", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "total_calls": 0,
        "calls_with_quality": 0,
        "avg_quality_score": None,
        "connection_rate": 0.0,
        "failure_breakdown": {},
    }
