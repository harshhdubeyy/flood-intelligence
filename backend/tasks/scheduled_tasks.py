"""
Asynchronous Celery tasks for weather ingestion and ML risk inference.
Scheduled via Celery Beat or triggered on-demand by API routes.
"""

import asyncio
import logging
from backend.tasks.celery_app import celery_app
from backend.pipeline.weather_ingest import weather_ingest_service
from backend.ml.engine_a.xgboost_risk import risk_classifier
from backend.pipeline.social_collection import social_collection_service
from backend.pipeline.social_lifecycle import social_lifecycle_service
from backend.models.database import async_session_factory, engine

logger = logging.getLogger("fip.tasks")


@celery_app.task(
    name="backend.tasks.scheduled_tasks.task_ingest_weather_all_wards",
    bind=True,
    queue="weather_ingest",
)
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
        try:
            loop.run_until_complete(weather_ingest_service.close_redis())
        finally:
            loop.run_until_complete(engine.dispose())
            loop.close()


@celery_app.task(
    name="backend.tasks.scheduled_tasks.task_compute_all_ward_risk_scores",
    bind=True,
    queue="weather_ingest",
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
)
def task_compute_all_ward_risk_scores(self):
    """
    Celery task: Evaluates 15-minute hydrological flood risk index (Engine A)
    and updates ward_risk_scores table.
    """
    logger.info("Executing 15-minute hydrological risk scoring cycle...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(risk_classifier.compute_and_persist_all_wards())
        logger.info(f"Hydrological risk computation finished: {result}")
        return result
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


compute_ward_flood_risks = task_compute_all_ward_risk_scores


@celery_app.task(name="backend.tasks.scheduled_tasks.task_poll_and_ingest_social_signals", bind=True)
def task_poll_and_ingest_social_signals(self):
    """
    Collect public social records into the isolated social_ingest queue.
    This task is triggerable on demand and is deliberately not beat-scheduled.
    """
    logger.info("Starting authorized social API collection")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _run():
            async with async_session_factory() as session:
                return await social_collection_service.collect(session)

        result = loop.run_until_complete(_run())
        logger.info(
            "Social API collection completed",
            extra={"inserted_count": result["inserted_count"]},
        )
        return result
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


@celery_app.task(
    name="backend.tasks.scheduled_tasks.task_expire_social_posts",
    bind=True,
    queue="social_ingest",
)
def task_expire_social_posts(self):
    """Dry-run by default; expires only rows with an explicitly configured deadline."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _run():
            async with async_session_factory() as session:
                return await social_lifecycle_service.expire_due(session)

        return loop.run_until_complete(_run())
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


@celery_app.task(
    name="backend.tasks.scheduled_tasks.task_reconcile_social_sources",
    bind=True,
    queue="social_ingest",
)
def task_reconcile_social_sources(self):
    """Recheck a bounded set of due records only when lifecycle access is enabled."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _run():
            async with async_session_factory() as session:
                return await social_lifecycle_service.reconcile_due(session)

        return loop.run_until_complete(_run())
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()


@celery_app.task(
    name="backend.tasks.scheduled_tasks.task_retry_social_takedowns",
    bind=True,
    queue="social_ingest",
)
def task_retry_social_takedowns(self):
    """Retry only previously recorded source-redaction failures."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        async def _run():
            async with async_session_factory() as session:
                return await social_lifecycle_service.retry_takedowns(session)

        return loop.run_until_complete(_run())
    finally:
        try:
            loop.run_until_complete(engine.dispose())
        finally:
            loop.close()
