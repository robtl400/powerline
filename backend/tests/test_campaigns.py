"""Smoke tests for campaign and target endpoints."""

import hashlib
import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import AudioRecording
from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.campaign_target import CampaignTarget
from app.models.target import Target
from app.models.user import User
from app.services.call_state import load_call_state
from app.services.telephony.base import CallResult


async def test_create_campaign(
    client: AsyncClient, admin_user: User, admin_headers: dict
) -> None:
    name = f"New Campaign {uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/v1/campaigns", json={"name": name}, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == name
    assert data["status"] == "draft"
    assert data["target_count"] == 0
    assert data["session_count"] == 0
    assert data["completed_session_count"] == 0
    # Campaign cleanup is handled by the admin_user FK cascade (SET NULL on delete)
    # and will be cleaned up in subsequent runs via unique names.


async def test_list_campaigns(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/campaigns", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    ids = [c["id"] for c in body["items"]]
    assert str(campaign.id) in ids


async def test_get_campaign(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(campaign.id)
    assert resp.json()["targets"] == []


async def test_list_and_detail_report_session_counts(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_user: User,
    admin_headers: dict,
) -> None:
    """Only sessions Twilio connected count; one still at `initiated` does not."""
    quiet = Campaign(
        name=f"Quiet Campaign {uuid.uuid4().hex[:8]}",
        created_by_id=admin_user.id,
    )
    db.add(quiet)

    def _session(status: str) -> CallSession:
        return CallSession(
            campaign_id=campaign.id,
            connection_type="webrtc",
            twilio_call_sid=f"CAses{uuid.uuid4().hex[:20]}",
            status=status,
        )

    seeded = [_session("completed"), _session("in_progress"), _session("initiated")]
    db.add_all(seeded)
    await db.commit()

    try:
        listing = await client.get("/api/v1/campaigns?limit=500", headers=admin_headers)
        assert listing.status_code == 200, listing.text
        body = listing.json()

        by_id = {c["id"]: c for c in body["items"]}
        assert len(by_id) == len(body["items"])
        assert body["total"] == await db.scalar(select(func.count()).select_from(Campaign))

        assert by_id[str(campaign.id)]["session_count"] == 2
        assert by_id[str(campaign.id)]["completed_session_count"] == 1
        assert by_id[str(quiet.id)]["session_count"] == 0
        assert by_id[str(quiet.id)]["completed_session_count"] == 0

        detail = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=admin_headers)
        assert detail.json()["session_count"] == 2
        assert detail.json()["completed_session_count"] == 1

        quiet_detail = await client.get(f"/api/v1/campaigns/{quiet.id}", headers=admin_headers)
        assert quiet_detail.json()["session_count"] == 0
        assert quiet_detail.json()["completed_session_count"] == 0
    finally:
        await db.execute(delete(CallSession).where(CallSession.id.in_([s.id for s in seeded])))
        await db.execute(delete(Campaign).where(Campaign.id == quiet.id))
        await db.commit()


async def test_list_counts_ignore_campaigns_outside_the_page(
    client: AsyncClient,
    db: AsyncSession,
    admin_user: User,
    admin_headers: dict,
) -> None:
    """A page's counts are aggregated over the page's own campaigns only."""
    token = uuid.uuid4().hex[:8]
    older = Campaign(name=f"Paged {token} older", created_by_id=admin_user.id)
    db.add(older)
    await db.commit()

    newer = Campaign(name=f"Paged {token} newer", created_by_id=admin_user.id)
    db.add(newer)

    seeded = [
        CallSession(
            campaign_id=older.id,
            connection_type="webrtc",
            twilio_call_sid=f"CApage{uuid.uuid4().hex[:20]}",
            status="completed",
        )
    ]
    db.add_all(seeded)
    await db.commit()

    try:
        listing = await client.get(f"/api/v1/campaigns?q=Paged+{token}&limit=1", headers=admin_headers)
        assert listing.status_code == 200, listing.text
        body = listing.json()

        assert body["total"] == 2
        assert [c["id"] for c in body["items"]] == [str(newer.id)]
        assert body["items"][0]["session_count"] == 0
        assert body["items"][0]["completed_session_count"] == 0

        second = await client.get(
            f"/api/v1/campaigns?q=Paged+{token}&limit=1&skip=1", headers=admin_headers
        )
        assert [c["id"] for c in second.json()["items"]] == [str(older.id)]
        assert second.json()["items"][0]["session_count"] == 1
        assert second.json()["items"][0]["completed_session_count"] == 1
    finally:
        await db.execute(delete(CallSession).where(CallSession.id.in_([s.id for s in seeded])))
        await db.execute(delete(Campaign).where(Campaign.id.in_([older.id, newer.id])))
        await db.commit()


async def test_campaign_not_found(client: AsyncClient, admin_headers: dict) -> None:
    resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404


async def test_valid_status_transition(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    # draft -> live is valid
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"status": "live"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "live"


async def test_invalid_status_transition(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    # draft -> archived is NOT a valid transition
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"status": "archived"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_add_and_remove_target(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Rep Smith",
            "title": "Representative",
            "phone_number": "+12025551234",
            "location": "CA-12",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    target_id = resp.json()["id"]

    del_resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}",
        headers=admin_headers,
    )
    assert del_resp.status_code == 204


async def test_reorder_targets(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    t1 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Target One",
            "title": "Rep",
            "phone_number": "+12025550001",
            "location": "WA-07",
        },
        headers=admin_headers,
    )
    t2 = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Target Two",
            "title": "Sen",
            "phone_number": "+12025550002",
            "location": "WA",
        },
        headers=admin_headers,
    )
    tid1 = t1.json()["id"]
    tid2 = t2.json()["id"]

    # Reorder: put t2 before t1
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}/targets/reorder",
        json={"target_ids": [tid2, tid1]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    reordered = resp.json()
    assert reordered[0]["id"] == tid2
    assert reordered[1]["id"] == tid1
    # Targets and CampaignTargets are cleaned up by the campaign fixture teardown.


async def test_campaigns_require_auth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/campaigns")
    assert resp.status_code == 401


async def test_staff_can_read_campaigns(
    client: AsyncClient, campaign: Campaign, staff_headers: dict
) -> None:
    """Staff see the campaign list, one campaign, and its checklist."""
    listed = await client.get("/api/v1/campaigns", headers=staff_headers)
    assert listed.status_code == 200

    detail = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=staff_headers)
    assert detail.status_code == 200

    checklist = await client.get(
        f"/api/v1/campaigns/{campaign.id}/checklist", headers=staff_headers
    )
    assert checklist.status_code == 200


async def test_campaign_writes_require_admin(
    client: AsyncClient, campaign: Campaign, staff_headers: dict
) -> None:
    """Reads are open to staff; anything that changes a campaign is not."""
    created = await client.post(
        "/api/v1/campaigns",
        json={"name": "Staff Attempt"},
        headers=staff_headers,
    )
    assert created.status_code == 403

    patched = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"name": "Renamed by staff"},
        headers=staff_headers,
    )
    assert patched.status_code == 403


async def test_target_invalid_phone(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Rep X",
            "title": "Rep",
            "phone_number": "not-a-phone",
            "location": "CA",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Enum-valued inputs are rejected at validation, not at the database
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"campaign_type": "not_a_type"},
    {"target_ordering": "backwards"},
    {"language": "en-US-extended"},
])
async def test_create_campaign_rejects_bad_enum(
    client: AsyncClient, admin_headers: dict, payload: dict
) -> None:
    body = {"name": f"Bad Enum {uuid.uuid4().hex[:8]}", **payload}
    resp = await client.post("/api/v1/campaigns", json=body, headers=admin_headers)
    assert resp.status_code == 422


@pytest.mark.parametrize("payload", [
    {"campaign_type": "not_a_type"},
    {"target_ordering": "backwards"},
    {"language": "en-US-extended"},
    {"status": "retired"},
])
async def test_update_campaign_rejects_bad_enum(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, payload: dict
) -> None:
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}", json=payload, headers=admin_headers
    )
    assert resp.status_code == 422


async def test_list_campaigns_rejects_bad_status_filter(
    client: AsyncClient, admin_headers: dict
) -> None:
    resp = await client.get("/api/v1/campaigns?status=retired", headers=admin_headers)
    assert resp.status_code == 422


async def test_list_campaigns_search_filters_by_name(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    """?q= narrows the list to name matches and excludes everything else."""
    other = Campaign(name=f"Unrelated Drive {uuid.uuid4().hex[:8]}", created_by_id=campaign.created_by_id)
    db.add(other)
    await db.commit()
    await db.refresh(other)

    try:
        term = campaign.name.split(" ")[-1]
        resp = await client.get(f"/api/v1/campaigns?q={term}", headers=admin_headers)
        assert resp.status_code == 200
        body = resp.json()
        ids = [c["id"] for c in body["items"]]
        assert str(campaign.id) in ids
        assert str(other.id) not in ids
        assert body["total"] == len(ids)

        # Wildcards in the term are literal, not LIKE metacharacters.
        wild = await client.get("/api/v1/campaigns?q=%25", headers=admin_headers)
        assert wild.status_code == 200
        assert str(campaign.id) not in [c["id"] for c in wild.json()["items"]]
    finally:
        await db.execute(delete(Campaign).where(Campaign.id == other.id))
        await db.commit()


async def test_list_campaigns_pagination(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """skip/limit bound the page while total counts everything the filters match."""
    term = campaign.name.split(" ")[-1]

    page = await client.get(
        f"/api/v1/campaigns?q={term}&skip=0&limit=1", headers=admin_headers
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 1
    assert [c["id"] for c in body["items"]] == [str(campaign.id)]

    past_the_end = await client.get(
        f"/api/v1/campaigns?q={term}&skip=1&limit=1", headers=admin_headers
    )
    assert past_the_end.json()["items"] == []
    assert past_the_end.json()["total"] == 1

    assert (
        await client.get("/api/v1/campaigns?limit=501", headers=admin_headers)
    ).status_code == 422


# ---------------------------------------------------------------------------
# remove_target: detach, then delete only when nothing else references it
# ---------------------------------------------------------------------------

async def test_remove_target_deletes_unreferenced_target(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Lonely Target",
            "title": "Rep",
            "phone_number": "+12025557001",
            "location": "CA-01",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert await db.get(Target, target_id) is None


async def test_remove_target_keeps_target_with_call_history(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    """A target a Call points at survives removal so history stays readable."""
    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Historic Target",
            "title": "Senator",
            "phone_number": "+12025557002",
            "location": "WA",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])

    session = CallSession(
        campaign_id=campaign.id,
        connection_type="outbound_phone",
        twilio_call_sid=f"CAhist{uuid.uuid4().hex[:20]}",
        status="completed",
    )
    db.add(session)
    await db.flush()
    call = Call(
        session_id=session.id,
        campaign_id=campaign.id,
        target_id=target_id,
        twilio_call_sid=f"CAleg{uuid.uuid4().hex[:20]}",
        status="completed",
    )
    db.add(call)
    await db.commit()

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204

    survivor = await db.get(Target, target_id)
    assert survivor is not None

    ct_left = await db.scalar(
        select(func.count())
        .select_from(CampaignTarget)
        .where(CampaignTarget.target_id == target_id)
    )
    assert ct_left == 0

    await db.execute(delete(Call).where(Call.id == call.id))
    await db.execute(delete(CallSession).where(CallSession.id == session.id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


async def test_remove_target_keeps_target_shared_with_another_campaign(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_user: User,
    admin_headers: dict,
) -> None:
    """A target still attached elsewhere is only detached, never deleted."""
    other = Campaign(
        name=f"Other Campaign {uuid.uuid4().hex[:8]}", created_by_id=admin_user.id
    )
    db.add(other)
    await db.flush()

    created = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Shared Target",
            "title": "Rep",
            "phone_number": "+12025557003",
            "location": "NY-10",
        },
        headers=admin_headers,
    )
    target_id = uuid.UUID(created.json()["id"])
    db.add(CampaignTarget(campaign_id=other.id, target_id=target_id, order=0))
    await db.commit()

    resp = await client.delete(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}", headers=admin_headers
    )
    assert resp.status_code == 204
    assert await db.get(Target, target_id) is not None

    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id == target_id))
    await db.execute(delete(Campaign).where(Campaign.id == other.id))
    await db.commit()
    await db.execute(delete(Target).where(Target.id == target_id))
    await db.commit()


# ---------------------------------------------------------------------------
# PATCH: every editable field round-trips
# ---------------------------------------------------------------------------


async def test_update_campaign_writes_every_editable_field(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    updates = {
        "name": f"Renamed {uuid.uuid4().hex[:8]}",
        "description": "A fuller description",
        "campaign_type": "custom",
        "language": "es-MX",
        "target_ordering": "shuffle",
        "call_maximum": 250,
        "rate_limit": 9,
        "allow_webrtc": False,
        "allow_phone_callback": False,
        "lookup_validate": False,
        "lookup_require_mobile": True,
        "embed_config": {"target_levels": ["federal"]},
        "talking_points": "Ask them to vote yes.",
    }

    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}", json=updates, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for field, value in updates.items():
        assert body[field] == value, field

    fetched = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=admin_headers)
    assert fetched.status_code == 200
    for field, value in updates.items():
        assert fetched.json()[field] == value, field


# ---------------------------------------------------------------------------
# POST /{id}/archive
# ---------------------------------------------------------------------------


async def test_archive_rejects_a_draft_campaign(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    """draft has no archived transition — it must be paused or live first."""
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/archive", headers=admin_headers
    )
    assert resp.status_code == 422
    assert "draft" in resp.json()["detail"]


async def test_archive_a_paused_campaign_then_refuses_to_repeat(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    campaign.status = "paused"
    await db.commit()

    archived = await client.post(
        f"/api/v1/campaigns/{campaign.id}/archive", headers=admin_headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    again = await client.post(
        f"/api/v1/campaigns/{campaign.id}/archive", headers=admin_headers
    )
    assert again.status_code == 422
    assert "archived" in again.json()["detail"]


async def test_archive_requires_admin(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, staff_headers: dict
) -> None:
    campaign.status = "live"
    await db.commit()

    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/archive", headers=staff_headers
    )
    assert resp.status_code == 403


async def test_a_name_frees_up_once_its_campaign_is_archived(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    """The unique index only covers non-archived campaigns."""
    name = campaign.name

    clash = await client.post("/api/v1/campaigns", json={"name": name}, headers=admin_headers)
    assert clash.status_code == 409, clash.text

    campaign.status = "paused"
    await db.commit()
    assert (
        await client.post(f"/api/v1/campaigns/{campaign.id}/archive", headers=admin_headers)
    ).status_code == 200

    reused = await client.post("/api/v1/campaigns", json={"name": name}, headers=admin_headers)
    assert reused.status_code == 201, reused.text

    await db.execute(delete(Campaign).where(Campaign.id == uuid.UUID(reused.json()["id"])))
    await db.commit()


# ---------------------------------------------------------------------------
# GET /{id}/checklist
# ---------------------------------------------------------------------------


async def test_checklist_tracks_targets_audio_and_talking_points(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    empty = await client.get(
        f"/api/v1/campaigns/{campaign.id}/checklist", headers=admin_headers
    )
    assert empty.status_code == 200, empty.text
    assert empty.json() == {
        "targets_configured": False,
        "audio_configured": False,
        "phone_number_assigned": False,
        "phone_verified": False,
        "talking_points_written": False,
    }

    added = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "Checklist Target",
            "title": "Rep",
            "phone_number": "+12025558001",
            "location": "OR-03",
        },
        headers=admin_headers,
    )
    assert added.status_code == 201, added.text

    recording = AudioRecording(
        campaign_id=campaign.id,
        key="msg_intro",
        version=1,
        tts_text="Welcome",
        is_active=True,
    )
    db.add(recording)
    await db.commit()

    patched = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"talking_points": "Ask for a yes vote."},
        headers=admin_headers,
    )
    assert patched.status_code == 200, patched.text

    filled = await client.get(
        f"/api/v1/campaigns/{campaign.id}/checklist", headers=admin_headers
    )
    assert filled.status_code == 200
    assert filled.json() == {
        "targets_configured": True,
        "audio_configured": True,
        "phone_number_assigned": False,
        "phone_verified": False,
        "talking_points_written": True,
    }

    await db.execute(delete(AudioRecording).where(AudioRecording.id == recording.id))
    await db.commit()


async def test_checklist_ignores_whitespace_only_talking_points(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    patched = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"talking_points": "   \n  "},
        headers=admin_headers,
    )
    assert patched.status_code == 200

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}/checklist", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["talking_points_written"] is False


# ---------------------------------------------------------------------------
# GET /{id}/count — public, live-only, rate limited, cached for ten minutes
# ---------------------------------------------------------------------------

_COUNT_RATE_KEY = "rate:count:127.0.0.1"
_PUBLIC_RATE_KEY = "rate:public:127.0.0.1"


@pytest.fixture
async def clear_count_rate_limit(redis):
    """Drop the shared per-IP count bucket around every test that uses it."""
    await redis.delete(_COUNT_RATE_KEY)
    yield
    await redis.delete(_COUNT_RATE_KEY)


async def test_count_unknown_campaign_is_404(
    client: AsyncClient, clear_count_rate_limit: None
) -> None:
    resp = await client.get(f"/api/v1/campaigns/{uuid.uuid4()}/count")
    assert resp.status_code == 404


async def test_count_hides_a_campaign_that_is_not_live(
    client: AsyncClient, campaign: Campaign, clear_count_rate_limit: None
) -> None:
    """A draft campaign answers the same 404 as one that does not exist."""
    resp = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
    assert resp.status_code == 404


async def test_count_is_rate_limited_per_client_ip(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    redis,
    monkeypatch: pytest.MonkeyPatch,
    clear_count_rate_limit: None,
) -> None:
    """The bucket is PUBLIC_RATE_LIMIT, the budget both embed bootstrap calls share."""
    from app.config import settings

    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 3)

    campaign.status = "live"
    await db.commit()

    for _ in range(settings.PUBLIC_RATE_LIMIT):
        allowed = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
        assert allowed.status_code == 200, allowed.text

    blocked = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
    assert blocked.status_code == 429

    await redis.delete(f"campaign_count:{campaign.id}")


async def test_public_is_rate_limited_per_client_ip(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The public endpoint draws on the same PUBLIC_RATE_LIMIT budget."""
    from app.config import settings

    monkeypatch.setattr(settings, "PUBLIC_RATE_LIMIT", 3)

    campaign.status = "live"
    await db.commit()

    await redis.delete(_PUBLIC_RATE_KEY)
    try:
        for _ in range(settings.PUBLIC_RATE_LIMIT):
            allowed = await client.get(f"/api/v1/campaigns/{campaign.id}/public")
            assert allowed.status_code == 200, allowed.text

        blocked = await client.get(f"/api/v1/campaigns/{campaign.id}/public")
        assert blocked.status_code == 429
    finally:
        await redis.delete(_PUBLIC_RATE_KEY)


async def test_count_reports_completed_sessions_then_serves_the_cache(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    redis,
    clear_count_rate_limit: None,
) -> None:
    campaign.status = "live"
    await db.commit()

    cache_key = f"campaign_count:{campaign.id}"
    await redis.delete(cache_key)

    def _session(status: str) -> CallSession:
        return CallSession(
            campaign_id=campaign.id,
            connection_type="webrtc",
            twilio_call_sid=f"CAcnt{uuid.uuid4().hex[:20]}",
            status=status,
        )

    seeded = [_session("completed"), _session("completed"), _session("failed")]
    db.add_all(seeded)
    await db.commit()

    first = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
    assert first.status_code == 200, first.text
    assert first.json() == {"total": 2, "last_24h": 2, "last_7d": 2}

    later = _session("completed")
    db.add(later)
    await db.commit()

    cached = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
    assert cached.status_code == 200
    assert cached.json() == {"total": 2, "last_24h": 2, "last_7d": 2}

    await redis.delete(cache_key)
    fresh = await client.get(f"/api/v1/campaigns/{campaign.id}/count")
    assert fresh.json()["total"] == 3

    await redis.delete(cache_key)
    ids = [s.id for s in seeded] + [later.id]
    await db.execute(delete(CallSession).where(CallSession.id.in_(ids)))
    await db.commit()


async def test_renaming_onto_a_live_name_is_a_conflict(
    client: AsyncClient, db: AsyncSession, campaign: Campaign, admin_headers: dict
) -> None:
    other = await client.post(
        "/api/v1/campaigns",
        json={"name": f"Rename Target {uuid.uuid4().hex[:8]}"},
        headers=admin_headers,
    )
    assert other.status_code == 201, other.text
    other_id = uuid.UUID(other.json()["id"])

    clash = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"name": other.json()["name"]},
        headers=admin_headers,
    )
    assert clash.status_code == 409, clash.text

    still_named = await client.get(f"/api/v1/campaigns/{campaign.id}", headers=admin_headers)
    assert still_named.json()["name"] == campaign.name

    await db.execute(delete(Campaign).where(Campaign.id == other_id))
    await db.commit()


# ---------------------------------------------------------------------------
# target_ordering="shuffle": the stored call order is a permutation
# ---------------------------------------------------------------------------


async def _five_targets(
    client: AsyncClient, campaign_id: uuid.UUID, admin_headers: dict
) -> list[str]:
    ids: list[str] = []
    for i in range(5):
        resp = await client.post(
            f"/api/v1/campaigns/{campaign_id}/targets",
            json={
                "name": f"Shuffle Target {i}",
                "title": "Representative",
                "phone_number": f"+1202555910{i}",
                "location": "CA",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids


async def _drop_targets(db: AsyncSession, target_ids: list[str]) -> None:
    ids = [uuid.UUID(t) for t in target_ids]
    await db.execute(delete(CampaignTarget).where(CampaignTarget.target_id.in_(ids)))
    await db.commit()
    await db.execute(delete(Target).where(Target.id.in_(ids)))
    await db.commit()


async def test_shuffle_permutes_target_ids_on_calls_create(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shuffled campaign stores the permuted order, not the configured one."""
    ordered = await _five_targets(client, campaign.id, admin_headers)

    campaign.status = "live"
    campaign.target_ordering = "shuffle"
    campaign.allow_phone_callback = True
    campaign.lookup_validate = False
    campaign.rate_limit = 20
    await db.commit()

    monkeypatch.setattr("random.shuffle", lambda seq: seq.reverse())
    provider = MagicMock()
    provider.create_call.return_value = CallResult(sid="CAshuffle", status="queued")
    monkeypatch.setattr("app.api.v1.calls.get_provider", lambda: provider)

    phone = "+12025559110"
    rate_keys = [
        "rate:call-ip:127.0.0.1",
        f"rate:call:{hashlib.sha256(phone.encode()).hexdigest()}",
    ]
    await redis.delete(*rate_keys)

    resp = await client.post(
        "/api/v1/calls/create",
        json={"campaign_id": str(campaign.id), "phone_number": phone},
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]

    state = await load_call_state(session_id)
    assert state["target_ids"] == list(reversed(ordered))

    await redis.delete(*rate_keys, f"call_session:{session_id}")
    await db.execute(delete(CallSession).where(CallSession.id == uuid.UUID(session_id)))
    await db.commit()
    await _drop_targets(db, ordered)


async def test_shuffle_permutes_target_ids_on_tokens_voice(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ordered = await _five_targets(client, campaign.id, admin_headers)

    campaign.status = "live"
    campaign.target_ordering = "shuffle"
    campaign.allow_webrtc = True
    campaign.rate_limit = 20
    await db.commit()

    monkeypatch.setattr("random.shuffle", lambda seq: seq.reverse())
    monkeypatch.setattr("app.api.v1.tokens._build_access_token", lambda session_id: "dev-token")

    rate_keys = ["rate:token:127.0.0.1", f"rate:token-campaign:{campaign.id}"]
    await redis.delete(*rate_keys)

    resp = await client.post(
        "/api/v1/tokens/voice", json={"campaign_id": str(campaign.id)}
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]

    state = await load_call_state(session_id)
    assert state["target_ids"] == list(reversed(ordered))

    await redis.delete(*rate_keys, f"call_session:{session_id}")
    await db.execute(delete(CallSession).where(CallSession.id == uuid.UUID(session_id)))
    await db.commit()
    await _drop_targets(db, ordered)


async def test_in_order_campaigns_keep_the_configured_order(
    client: AsyncClient,
    db: AsyncSession,
    campaign: Campaign,
    admin_headers: dict,
    redis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same reversing shuffle is never reached when ordering is in_order."""
    ordered = await _five_targets(client, campaign.id, admin_headers)

    campaign.status = "live"
    campaign.allow_webrtc = True
    campaign.rate_limit = 20
    await db.commit()

    monkeypatch.setattr("random.shuffle", lambda seq: seq.reverse())
    monkeypatch.setattr("app.api.v1.tokens._build_access_token", lambda session_id: "dev-token")

    rate_keys = ["rate:token:127.0.0.1", f"rate:token-campaign:{campaign.id}"]
    await redis.delete(*rate_keys)

    resp = await client.post(
        "/api/v1/tokens/voice", json={"campaign_id": str(campaign.id)}
    )
    assert resp.status_code == 200, resp.text
    session_id = resp.json()["session_id"]

    state = await load_call_state(session_id)
    assert state["target_ids"] == ordered

    await redis.delete(*rate_keys, f"call_session:{session_id}")
    await db.execute(delete(CallSession).where(CallSession.id == uuid.UUID(session_id)))
    await db.commit()
    await _drop_targets(db, ordered)


# ---------------------------------------------------------------------------
# GET /{id}: bounded target list
# ---------------------------------------------------------------------------


async def _add_targets(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, count: int
) -> list[str]:
    ids = []
    for i in range(count):
        resp = await client.post(
            f"/api/v1/campaigns/{campaign.id}/targets",
            json={
                "name": f"Target {i}",
                "title": "Rep",
                "phone_number": f"+1202555{2000 + i:04d}",
                "location": "WA-07",
            },
            headers=admin_headers,
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids


async def test_get_campaign_caps_the_target_list_and_reports_the_total(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    ids = await _add_targets(client, campaign, admin_headers, 3)

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}?targets_limit=2", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [t["id"] for t in body["targets"]] == ids[:2]
    assert body["targets_total"] == 3
    assert body["target_count"] == 3


async def test_get_campaign_can_skip_the_target_list(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    await _add_targets(client, campaign, admin_headers, 2)

    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}?include_targets=false", headers=admin_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["targets"] == []
    assert body["targets_total"] == 2


async def test_get_campaign_rejects_an_unbounded_targets_limit(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.get(
        f"/api/v1/campaigns/{campaign.id}?targets_limit=5000", headers=admin_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH: status transitions are applied conditionally
# ---------------------------------------------------------------------------


async def test_status_change_conflicts_when_the_campaign_moved_underneath(
    client: AsyncClient, campaign: Campaign, admin_headers: dict, db: AsyncSession
) -> None:
    """draft -> live passes the transition check, but the row is already paused."""
    from app.api.v1 import campaigns as campaigns_module

    real_get = campaigns_module.get_campaign_or_404

    async def stale_read(campaign_id, session):
        fetched = await real_get(campaign_id, session)
        await db.execute(
            update(Campaign).where(Campaign.id == campaign_id).values(status="paused")
        )
        await db.commit()
        return fetched

    with patch.object(campaigns_module, "get_campaign_or_404", stale_read):
        resp = await client.patch(
            f"/api/v1/campaigns/{campaign.id}",
            json={"status": "live"},
            headers=admin_headers,
        )

    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "Campaign status changed, reload and try again"

    fetched = await client.get(
        f"/api/v1/campaigns/{campaign.id}?include_targets=false", headers=admin_headers
    )
    assert fetched.json()["status"] == "paused"


async def test_status_change_and_other_fields_apply_together(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    new_name = f"Renamed {uuid.uuid4().hex[:8]}"
    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}",
        json={"status": "live", "name": new_name, "rate_limit": 4},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "live"
    assert body["name"] == new_name
    assert body["rate_limit"] == 4


# ---------------------------------------------------------------------------
# Target field lengths are bounded by the column widths
# ---------------------------------------------------------------------------


async def test_add_target_rejects_an_over_long_name(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    resp = await client.post(
        f"/api/v1/campaigns/{campaign.id}/targets",
        json={
            "name": "N" * 201,
            "title": "Rep",
            "phone_number": "+12025551234",
            "location": "CA-12",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


async def test_update_target_rejects_an_over_long_title(
    client: AsyncClient, campaign: Campaign, admin_headers: dict
) -> None:
    target_id = (await _add_targets(client, campaign, admin_headers, 1))[0]

    resp = await client.patch(
        f"/api/v1/campaigns/{campaign.id}/targets/{target_id}",
        json={"title": "T" * 101},
        headers=admin_headers,
    )
    assert resp.status_code == 422
