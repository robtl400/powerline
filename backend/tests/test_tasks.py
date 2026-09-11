"""Unit tests for the periodic-task helpers.

The task bodies themselves need a synchronous DB session and a live Twilio
account, so they are verified manually (see README → Celery). What is tested
here is the logic that decides whether a run happens at all and which rows it
would touch.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.call import Call
from app.models.call_session import CallSession
from app.models.campaign import Campaign
from app.models.target import Target
from app.tasks.cleanup import REP_LOOKUP_EXTERNAL_ID, stale_rep_targets_query
from app.tasks.insights import candidate_calls_query
from app.tasks.lock import acquire, release, task_lock


class FakeRedis:
    """Minimal stand-in supporting the SET NX EX / owner-checked DEL pair."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


def test_acquire_is_exclusive_until_released() -> None:
    client = FakeRedis()

    first = acquire(client, "lock:test", 60)
    assert first is not None
    assert client.ttls["lock:test"] == 60

    assert acquire(client, "lock:test", 60) is None

    assert release(client, "lock:test", first) is True
    assert acquire(client, "lock:test", 60) is not None


def test_release_ignores_a_lock_owned_by_someone_else() -> None:
    """A run that overran its TTL must not free the lock a later run holds."""
    client = FakeRedis()
    stale = acquire(client, "lock:test", 60)
    assert stale is not None
    release(client, "lock:test", stale)

    current = acquire(client, "lock:test", 60)
    assert release(client, "lock:test", stale) is False
    assert client.store["lock:test"] == current


def test_task_lock_releases_even_when_the_body_raises() -> None:
    client = FakeRedis()

    try:
        with task_lock(client, "lock:test", 60) as acquired:
            assert acquired
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert "lock:test" not in client.store


def test_task_lock_reports_a_contended_lock() -> None:
    client = FakeRedis()

    with task_lock(client, "lock:test", 60) as outer:
        assert outer
        with task_lock(client, "lock:test", 60) as inner:
            assert not inner

    assert "lock:test" not in client.store


def test_insights_query_filters_on_quality_details_not_score() -> None:
    """A fetched-but-unscored call has quality_details set, so it is not refetched."""
    sql = str(candidate_calls_query(datetime.now(timezone.utc) - timedelta(hours=24)))

    assert "calls.quality_details IS NULL" in sql
    assert "quality_score" not in sql
    assert "calls.status = " in sql


def test_cleanup_query_spares_referenced_and_recent_targets() -> None:
    sql = str(stale_rep_targets_query(datetime.now(timezone.utc) - timedelta(days=30)))

    assert sql.startswith("DELETE FROM targets")
    assert "targets.external_id = " in sql
    assert "targets.created_at < " in sql
    assert "NOT (EXISTS" in sql
    assert "campaign_targets" in sql
    assert "calls" in sql
    assert REP_LOOKUP_EXTERNAL_ID == "rep_lookup"


def _rep_target(name: str, age_days: int) -> Target:
    return Target(
        name=name,
        title="Representative",
        phone_number="+12025556100",
        location="WA-07",
        external_id=REP_LOOKUP_EXTERNAL_ID,
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


async def test_cleanup_keeps_a_rep_target_a_call_still_points_at(
    db: AsyncSession, campaign: Campaign
) -> None:
    """Deleting it would drop the call from per-target analytics, which inner-join Target."""
    called = _rep_target("Rep. Logged", 60)
    orphan = _rep_target("Rep. Unused", 60)
    db.add_all([called, orphan])
    await db.flush()

    session = CallSession(
        campaign_id=campaign.id,
        connection_type="webrtc",
        twilio_call_sid=f"CAclean{uuid.uuid4().hex[:20]}",
        status="completed",
    )
    db.add(session)
    await db.flush()

    db.add(
        Call(
            session_id=session.id,
            campaign_id=campaign.id,
            target_id=called.id,
            twilio_call_sid=f"CAleg{uuid.uuid4().hex[:20]}",
            status="completed",
            duration=30,
        )
    )
    await db.flush()

    called_id, orphan_id, session_id = called.id, orphan.id, session.id
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        await db.execute(stale_rep_targets_query(cutoff))

        survivors = (
            await db.execute(
                select(Target.id).where(Target.id.in_([called_id, orphan_id]))
            )
        ).scalars().all()
        assert set(survivors) == {called_id}
    finally:
        await db.execute(delete(Call).where(Call.session_id == session_id))
        await db.execute(delete(CallSession).where(CallSession.id == session_id))
        await db.execute(delete(Target).where(Target.id.in_([called_id, orphan_id])))
        await db.commit()
