"""Weather-only Celery Beat app, isolated from the shared schedule."""

from celery import Celery

from backend.config import get_settings

settings = get_settings()

weather_beat_app = Celery(
    "flood_intelligence_weather_beat",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
weather_beat_app.conf.update(
    timezone="Asia/Kolkata",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_routes={
        "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards": {
            "queue": "weather_ingest",
        },
        "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores": {
            "queue": "weather_ingest",
        },
    },
    beat_schedule={
        "ingest-weather-every-10-min": {
            "task": "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards",
            "schedule": 600.0,
            "options": {"queue": "weather_ingest"},
        },
        "compute-ward-risk-scores-every-15-min": {
            "task": "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores",
            "schedule": 900.0,
            "options": {"queue": "weather_ingest"},
        },
    },
)
