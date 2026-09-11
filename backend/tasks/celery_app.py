"""
Celery application instance and asynchronous task queue configuration.
Connects to Redis broker and configures Celery Beat scheduled jobs.
"""

from celery import Celery
from celery.schedules import crontab
from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "flood_intelligence",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["backend.tasks.scheduled_tasks"]
)

# Celery Task Execution Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,        # 5 minutes max per task
    task_soft_time_limit=240,
    broker_connection_retry_on_startup=True,
)

# Celery Beat Scheduled Crons per TRD Section 8.2 & 12
celery_app.conf.beat_schedule = {
    # Ingest weather observations from OpenWeatherMap & Open-Meteo every 10 minutes
    "ingest-weather-every-10-min": {
        "task": "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards",
        "schedule": 600.0,  # 10 minutes (600s)
    },
    # Execute ML Risk Classifier (Engine A) every 15 minutes
    "compute-ward-risk-scores-every-15-min": {
        "task": "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores",
        "schedule": 900.0,  # 15 minutes (900s)
    },
    # Ingest Social Signals (Engine C) every 5 minutes
    "poll-social-media-every-5-min": {
        "task": "backend.tasks.scheduled_tasks.task_poll_and_ingest_social_signals",
        "schedule": 300.0,  # 5 minutes (300s)
    },
}
