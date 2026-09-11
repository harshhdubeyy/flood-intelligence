"""
Asynchronous Celery tasks for weather ingestion and ML risk inference.
Scheduled via Celery Beat or triggered on-demand by API routes.
"""

import asyncio
import logging
from backend.tasks.celery_app import celery_app
from backend.pipeline.weather_ingest import weather_ingest_service
from backend.ml.engine_a.xgboost_risk import risk_classifier
from backend.pipeline.social_ingest import social_ingest_pipeline
from backend.models.database import AsyncSessionLocal

logger = logging.getLogger("fip.tasks")


@celery_app.task(name="backend.tasks.scheduled_tasks.task_ingest_weather_all_wards", bind=True)
def task_ingest_weather_all_wards(self):
    """
    Celery task: Ingests real-time precipitation and meteorological data
    for all Mumbai wards from OpenWeatherMap & Open-Meteo.
    """
    logger.info("Executing scheduled weather ingestion across all wards...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(weather_ingest_service.ingest_all_wards())
        logger.info(f"Weather ingestion finished: {result}")
        return result
    finally:
        loop.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores", bind=True)
def task_compute_all_ward_risk_scores(self):
    """
    Celery task: Evaluates 15-minute XGBoost flood risk classifier (Engine A)
    and updates ward_risk_scores table.
    """
    logger.info("Executing 15-minute ML risk inference cycle...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(risk_classifier.compute_and_persist_all_wards())
        logger.info(f"ML risk computation finished: {result}")
        return result
    finally:
        loop.close()


@celery_app.task(name="backend.tasks.scheduled_tasks.task_poll_and_ingest_social_signals", bind=True)
def task_poll_and_ingest_social_signals(self):
    """
    Celery task: Ingests recent social media intelligence, runs Engine C NLP,
    and updates ward situational awareness caches.
    """
    logger.info("Executing scheduled social intelligence ingestion...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _run():
            async with AsyncSessionLocal() as session:
                return await social_ingest_pipeline.ingest_simulation_batch(session)

        created = loop.run_until_complete(_run())
        logger.info(f"Social ingestion processed {len(created)} items")
        return {"ingested_count": len(created)}
    finally:
        loop.close()

