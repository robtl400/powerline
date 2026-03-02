"""Voice Insights background task.

Runs every 15 minutes via Celery Beat to fetch call quality scores from the
Twilio Voice Insights API for recently completed calls.

Uses a synchronous SQLAlchemy engine (psycopg2) because Celery workers run in
a sync context. The DATABASE_URL from settings uses '+asyncpg'; we swap it for
'+psycopg2' here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings

log = logging.getLogger(__name__)

# How far back to look for un-scored completed calls.
_LOOKBACK_HOURS = 24


def _get_sync_engine():
    """Build a synchronous SQLAlchemy engine from the async DATABASE_URL."""
    sync_url = settings.DATABASE_URL.replace("+asyncpg", "+psycopg2").replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    # Remove asyncpg-specific options that psycopg2 doesn't understand
    if "postgresql://" in sync_url and "+psycopg2" not in sync_url:
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg2://")
    return create_engine(sync_url, pool_pre_ping=True)


def _fetch_summary(call_sid: str) -> dict | None:
    """Call Twilio Voice Insights API for a single call SID.

    Returns a dict with quality_score and quality_details, or None on failure.
    """
    try:
        from twilio.rest import Client as TwilioClient

        client = TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
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


@celery_app.task(name="app.tasks.insights.fetch_voice_insights", bind=True, max_retries=0)
def fetch_voice_insights(self) -> dict:
    """Fetch Voice Insights quality scores for recent completed calls.

    Skipped entirely in dev when Twilio credentials are absent.
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        log.info("voice_insights_skipped: no Twilio credentials")
        return {"skipped": True, "reason": "no_twilio_credentials"}

    # Import models in dependency order — CallSession must be registered with
    # SQLAlchemy's mapper before Call, because Call.session uses relationship("CallSession").
    from app.models.call_session import CallSession  # noqa: F401 — registers mapper
    from app.models.call import Call

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)

    engine = _get_sync_engine()
    updated = 0
    errors = 0

    with Session(engine) as db:
        # Find completed calls in the last 24h without a quality score
        result = db.execute(
            select(Call.id, Call.twilio_call_sid).where(
                Call.status == "completed",
                Call.quality_score.is_(None),
                Call.created_at >= cutoff,
                Call.twilio_call_sid != "",
            )
        )
        rows = result.all()

        log.info("voice_insights_task_start", extra={"candidate_calls": len(rows)})

        for call_id, call_sid in rows:
            data = _fetch_summary(call_sid)
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
