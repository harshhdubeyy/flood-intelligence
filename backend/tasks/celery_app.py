"""
Celery application instance and asynchronous task queue configuration.
Connects to Redis broker and configures Celery Beat scheduled jobs.
"""

from celery import Celery
from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "flood_intelligence",
    broker=settings.redis_url,
    backend=settings.redis_url,
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
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards": {
            "queue": "weather_ingest",
        },
        "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores": {
            "queue": "weather_ingest",
        },
        "backend.tasks.scheduled_tasks.task_poll_and_ingest_social_signals": {
            "queue": "social_ingest",
        },
        "backend.tasks.scheduled_tasks.task_expire_social_posts": {
            "queue": "social_ingest",
        },
        "backend.tasks.scheduled_tasks.task_reconcile_social_sources": {
            "queue": "social_ingest",
        },
        "backend.tasks.scheduled_tasks.task_retry_social_takedowns": {
            "queue": "social_ingest",
        },
    },
)

# Celery Beat Scheduled Crons per TRD Section 8.2 & 12
celery_app.conf.beat_schedule = {
    # Ingest weather observations from OpenWeatherMap & Open-Meteo every 10 minutes
    "ingest-weather-every-10-min": {
        "task": "backend.tasks.scheduled_tasks.task_ingest_weather_all_wards",
        "schedule": 600.0,  # 10 minutes (600s)
        "options": {"queue": "weather_ingest"},
    },
    # Execute ML Risk Classifier (Engine A) every 15 minutes
    "compute-ward-risk-scores-every-15-min": {
        "task": "backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores",
        "schedule": 900.0,  # 15 minutes (900s)
        "options": {"queue": "weather_ingest"},
    },
}
