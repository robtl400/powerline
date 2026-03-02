from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "powerline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.insights"],
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
}
