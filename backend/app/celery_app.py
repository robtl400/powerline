from celery import Celery
from celery.schedules import crontab

from app.config import settings
from app.redis_client import redis_url_with_password

_broker_url = redis_url_with_password(settings.REDIS_URL, settings.REDIS_PASSWORD)

celery_app = Celery(
    "powerline",
    broker=_broker_url,
    backend=_broker_url,
    include=["app.tasks.insights", "app.tasks.cleanup"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Periodic task schedule (used by celery-beat service).
celery_app.conf.beat_schedule = {
    # Fetch Twilio Voice Insights quality scores for recent completed calls.
    # Only processes calls from the last 24h with no score yet.
    "fetch-voice-insights-every-15min": {
        "task": "app.tasks.insights.fetch_voice_insights",
        "schedule": crontab(minute="*/15"),
    },
    # Drop rep-lookup targets that no campaign references any more.
    "cleanup-rep-targets-daily": {
        "task": "app.tasks.cleanup.cleanup_rep_targets",
        "schedule": crontab(hour="4", minute="20"),
    },
}
