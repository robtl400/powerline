"""Voice Insights background task.

Runs every 15 minutes via Celery Beat to fetch call quality scores from the
Twilio Voice Insights API for recently completed calls.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.tasks.db import get_engine, get_redis
from app.tasks.lock import task_lock

log = logging.getLogger(__name__)

# How far back to look for un-scored completed calls.
_LOOKBACK_HOURS = 24

# Beat fires every 15 minutes. The TTL covers a run that overruns several ticks
# — a slow Twilio API must not let a second worker start the same fetch — and
# still expires on its own, so a crashed worker cannot wedge the schedule.
_LOCK_KEY = "lock:voice_insights"
_LOCK_TTL = 1500

# Twilio rate-limits the Insights API, so keep the fan-out modest.
_MAX_WORKERS = 4


def candidate_calls_query(cutoff: datetime) -> Select:
    """Select completed calls that have never been through Insights.

    Keyed on quality_details rather than quality_score: Twilio returns no score
    for calls it has not finished processing, and a row that came back scoreless
    still has its processing state recorded, so it is not fetched again on
    every cycle.
    """
    from app.models.call_session import CallSession  # noqa: F401 — registers mapper
    from app.models.call import Call

    return select(Call.id, Call.twilio_call_sid).where(
        Call.status == "completed",
        Call.quality_details.is_(None),
        Call.created_at >= cutoff,
        Call.twilio_call_sid != "",
    )


def _fetch_summary(client: Any, call_sid: str) -> dict | None:
    """Call Twilio Voice Insights API for a single call SID.

    Returns a dict with quality_score and quality_details, or None on failure.
    """
    try:
        summary = client.insights.v1.calls(call_sid).summary.fetch()

        quality_details: dict = {
            "processing_state": summary.processing_state,
        }
        # Include edge metrics if present
        if summary.carrier_edge:
            quality_details["carrier_edge"] = summary.carrier_edge
        if hasattr(summary, "client_edge") and summary.client_edge:
            quality_details["client_edge"] = summary.client_edge
        if hasattr(summary, "sdk_edge") and summary.sdk_edge:
            quality_details["sdk_edge"] = summary.sdk_edge

        return {
            "quality_score": float(summary.call_score) if summary.call_score is not None else None,
            "quality_details": quality_details,
        }
    except Exception:
        log.exception("voice_insights_fetch_failed", extra={"call_sid": call_sid[:10]})
        return None


def _run() -> dict:
    # Import models in dependency order — CallSession must be registered with
    # SQLAlchemy's mapper before Call, because Call.session uses relationship("CallSession").
    from app.models.call_session import CallSession  # noqa: F401 — registers mapper
    from app.models.call import Call

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)
    updated = 0
    errors = 0

    with Session(get_engine()) as db:
        rows = db.execute(candidate_calls_query(cutoff)).all()

        log.info("voice_insights_task_start", extra={"candidate_calls": len(rows)})

        if rows:
            from twilio.rest import Client as TwilioClient

            client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
                summaries = list(
                    pool.map(partial(_fetch_summary, client), [sid for _, sid in rows])
                )
        else:
            summaries = []

        for (call_id, _), data in zip(rows, summaries):
            if data is None:
                errors += 1
                continue

            db.execute(
                update(Call)
                .where(Call.id == call_id)
                .values(
                    quality_score=data["quality_score"],
                    quality_details=data["quality_details"],
                )
            )
            updated += 1

        db.commit()

    log.info("voice_insights_task_done", extra={"updated": updated, "errors": errors})
    return {"updated": updated, "errors": errors}


@celery_app.task(name="app.tasks.insights.fetch_voice_insights", bind=True, max_retries=0)
def fetch_voice_insights(self) -> dict:
    """Fetch Voice Insights quality scores for recent completed calls.

    Skipped entirely in dev when Twilio credentials are absent.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        log.info("voice_insights_skipped: no Twilio credentials")
        return {"skipped": True, "reason": "no_twilio_credentials"}

    with task_lock(get_redis(), _LOCK_KEY, _LOCK_TTL) as acquired:
        if not acquired:
            log.info("voice_insights_skipped: another run holds the lock")
            return {"skipped": True, "reason": "locked"}
        return _run()
