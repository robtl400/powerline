"""Housekeeping tasks for rows the call flow creates on the fly."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Delete, delete, exists
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.tasks.db import get_engine, get_redis
from app.tasks.lock import task_lock

log = logging.getLogger(__name__)

# Targets minted by a ZIP-code rep lookup are single-use: one supporter's
# representative, dialed once. They are kept long enough to serve retries and
# support questions, then dropped.
REP_LOOKUP_EXTERNAL_ID = "rep_lookup"
_RETENTION_DAYS = 30

_LOCK_KEY = "lock:cleanup_rep_targets"
_LOCK_TTL = 3300


def stale_rep_targets_query(cutoff: datetime) -> Delete:
    """Delete aged rep-lookup targets that no campaign still lists.

    Call.target_id is ON DELETE SET NULL, so call history outlives the target
    row it pointed at.
    """
    from app.models.campaign_target import CampaignTarget
    from app.models.target import Target

    return delete(Target).where(
        Target.external_id == REP_LOOKUP_EXTERNAL_ID,
        Target.created_at < cutoff,
        ~exists().where(CampaignTarget.target_id == Target.id),
    )


def _run() -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)

    with Session(get_engine()) as db:
        result = db.execute(stale_rep_targets_query(cutoff))
        db.commit()
        deleted = result.rowcount or 0

    log.info("cleanup_rep_targets_done", extra={"deleted": deleted})
    return {"deleted": deleted}


@celery_app.task(name="app.tasks.cleanup.cleanup_rep_targets", bind=True, max_retries=0)
def cleanup_rep_targets(self) -> dict:
    """Drop rep-lookup targets older than the retention window."""
    with task_lock(get_redis(), _LOCK_KEY, _LOCK_TTL) as acquired:
        if not acquired:
            log.info("cleanup_rep_targets_skipped: another run holds the lock")
            return {"skipped": True, "reason": "locked"}
        return _run()
