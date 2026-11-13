"""
Weather and forecast API endpoints for current conditions and triggerable ingestion.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from backend.config import get_settings
from backend.models.database import get_db
from backend.models.ward import Ward
from backend.models.weather import WeatherSnapshot
from backend.schemas.weather import (
    WeatherSnapshotResponse,
    WeatherForecastResponse,
    WeatherForecastItem,
    IngestionStatusResponse,
)
from backend.pipeline.weather_ingest import weather_ingest_service
from backend.ml.engine_a.xgboost_risk import risk_classifier
from backend.tasks.celery_app import celery_app

router = APIRouter(prefix="/weather", tags=["Weather"])
logger = logging.getLogger("fip.api.weather")
FORECAST_CACHE_TTL = timedelta(minutes=15)
SCHEDULER_HEARTBEAT_KEY = "fip:weather:scheduler:heartbeat"
INGESTION_STATUS_KEY = "fip:weather:ingestion:status"


def _fresh_forecast_timestamp(payload: Dict[str, Any], horizon: str, now: datetime) -> Optional[datetime]:
    horizon_key = f"forecast_fetched_at_{horizon}"
    has_horizon_timestamps = any(
        payload.get(f"forecast_fetched_at_{candidate}") for candidate in ("1h", "3h", "6h", "12h", "24h")
    )
    value = payload.get(horizon_key)
    if not has_horizon_timestamps:
        value = payload.get("fetched_at")
    if not isinstance(value, str):
        return None
    try:
        fetched_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    if fetched_at > now + timedelta(minutes=5) or now - fetched_at > FORECAST_CACHE_TTL:
        return None
    return fetched_at


async def _celery_availability() -> Dict[str, bool]:
    def inspect_workers() -> tuple[bool, bool]:
        inspector = celery_app.control.inspect(timeout=1.0)
        pings = inspector.ping() or {}
        queues = inspector.active_queues() or {}
        weather_worker = any(
            queue.get("name") == "weather_ingest"
            for worker_queues in queues.values()
            for queue in worker_queues
        )
        return bool(pings), weather_worker

    try:
        worker_available, weather_worker_available = await run_in_threadpool(inspect_workers)
    except Exception as exc:
        logger.warning("Celery availability inspection failed: %s", type(exc).__name__)
        return {"worker_available": False, "weather_worker_available": False}
    return {
        "worker_available": worker_available,
        "weather_worker_available": weather_worker_available,
    }


@router.get("/status", summary="Weather ingestion, forecast freshness, and scheduler status")
async def get_weather_ingestion_status(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    redis_client = aioredis.from_url(
        get_settings().redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    redis_connected = False
    ingestion_status: Dict[str, Any] = {}
    scheduler_available = False
    fresh_wards: set[str] = set()
    stale_wards: set[str] = set()
    horizon_counts = {horizon: 0 for horizon in ("1h", "3h", "6h", "12h", "24h")}
    try:
        await redis_client.ping()
        redis_connected = True
        raw_status = await redis_client.get(INGESTION_STATUS_KEY)
        if raw_status:
            try:
                status_payload = json.loads(raw_status)
                if isinstance(status_payload, dict):
                    ingestion_status = status_payload
            except json.JSONDecodeError:
                logger.warning("Weather ingestion monitoring key contains invalid JSON.")

        raw_heartbeat = await redis_client.get(SCHEDULER_HEARTBEAT_KEY)
        if raw_heartbeat:
            try:
                heartbeat = json.loads(raw_heartbeat)
                last_seen = datetime.fromisoformat(heartbeat["last_seen_at"].replace("Z", "+00:00"))
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                scheduler_available = timedelta(0) <= now - last_seen <= timedelta(seconds=60)
            except (KeyError, TypeError, ValueError):
                logger.warning("Weather scheduler heartbeat is malformed.")

        ward_ids = (await db.execute(select(Ward.ward_id))).scalars().all()
        for ward_id in ward_ids:
            raw_cache = await redis_client.get(f"fip:weather:latest:{ward_id}")
            if not raw_cache:
                continue
            try:
                cache_payload = json.loads(raw_cache)
            except json.JSONDecodeError:
                logger.warning("Weather forecast cache is malformed for ward %s.", ward_id)
                continue

            has_forecast = False
            has_fresh_forecast = False
            for horizon in horizon_counts:
                forecast_value = cache_payload.get(f"forecast_rain_{horizon}_mm")
                if forecast_value is None:
                    continue
                has_forecast = True
                if _fresh_forecast_timestamp(cache_payload, horizon, now) is not None:
                    horizon_counts[horizon] += 1
                    has_fresh_forecast = True
            if has_fresh_forecast:
                fresh_wards.add(ward_id)
            elif has_forecast:
                stale_wards.add(ward_id)
    except (RedisError, OSError) as exc:
        logger.warning("Weather status Redis read failed: %s", type(exc).__name__)
    finally:
        await redis_client.aclose()

    celery_status = await _celery_availability()
    return {
        "checked_at": now,
        "redis_connected": redis_connected,
        "last_ingestion_status": ingestion_status.get("last_status"),
        "last_ingestion_started_at": ingestion_status.get("last_started_at"),
        "last_ingestion_completed_at": ingestion_status.get("last_completed_at"),
        "last_successful_ingestion_at": ingestion_status.get("last_success_at"),
        "wards_total": ingestion_status.get("wards_total", 24),
        "wards_with_fresh_forecasts": len(fresh_wards),
        "wards_with_stale_forecasts": len(stale_wards),
        "wards_without_forecasts": max(
            0,
            int(ingestion_status.get("wards_total", 24)) - len(fresh_wards) - len(stale_wards),
        ),
        "fresh_forecasts_by_horizon": horizon_counts,
        "latest_errors": ingestion_status.get("latest_errors", []),
        "scheduler_available": scheduler_available,
        **celery_status,
    }


@router.get(
    "/{ward_id}/current",
    response_model=WeatherSnapshotResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve latest recorded weather snapshot for a ward"
)
async def get_current_weather(
    ward_id: str,
    db: AsyncSession = Depends(get_db)
) -> WeatherSnapshotResponse:
    """
    Fetch the most recent weather snapshot (rainfall, wind, humidity, tide).
    """
    stmt = (
        select(WeatherSnapshot)
        .where(WeatherSnapshot.ward_id == ward_id)
        .order_by(desc(WeatherSnapshot.fetched_at))
        .limit(1)
    )
    res = await db.execute(stmt)
    snapshot = res.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No weather records found for ward '{ward_id}'."
        )

    return WeatherSnapshotResponse.model_validate(snapshot)


@router.get(
    "/{ward_id}/forecast",
    response_model=WeatherForecastResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve 48-hour forward precipitation forecast for a ward"
)
async def get_ward_forecast(
    ward_id: str,
    db: AsyncSession = Depends(get_db)
) -> WeatherForecastResponse:
    """
    Query Open-Meteo for hourly forecast and computed 6h, 12h, 24h expected rainfall.
    """
    ward_stmt = select(Ward).where(Ward.ward_id == ward_id)
    ward_res = await db.execute(ward_stmt)
    ward = ward_res.scalar_one_or_none()

    if not ward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{ward_id}' not found."
        )

    # Fetch forecast directly
    async with httpx.AsyncClient() as client:
        # Default coordinates if geometry parsing not done
        lat = 19.0760
        lon = 72.8777
        meteo_data = await weather_ingest_service.fetch_open_meteo_forecast(client, lat, lon)

    hourly_data = meteo_data.get("hourly", {})
    times = hourly_data.get("time", [])
    rains = hourly_data.get("precipitation", []) or hourly_data.get("rain", [])
    winds = hourly_data.get("wind_speed_10m", [])

    forecast_items: List[WeatherForecastItem] = []
    for i in range(min(len(times), 24)):
        try:
            t_dt = datetime.fromisoformat(times[i])
        except Exception:
            t_dt = datetime.now(timezone.utc)

        forecast_items.append(
            WeatherForecastItem(
                timestamp=t_dt,
                rain_mm=float(rains[i]) if i < len(rains) else 0.0,
                wind_speed_kmh=float(winds[i]) if i < len(winds) else 15.0
            )
        )

    rain_6h = float(sum(rains[:6])) if len(rains) >= 6 else 0.0
    rain_12h = float(sum(rains[:12])) if len(rains) >= 12 else 0.0
    rain_24h = float(sum(rains[:24])) if len(rains) >= 24 else 0.0

    return WeatherForecastResponse(
        ward_id=ward_id,
        forecast_rain_6h_mm=round(rain_6h, 2),
        forecast_rain_12h_mm=round(rain_12h, 2),
        forecast_rain_24h_mm=round(rain_24h, 2),
        hourly=forecast_items
    )


@router.post(
    "/ingest",
    response_model=IngestionStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger immediate weather ingestion and ML risk inference cycle on-demand"
)
async def trigger_weather_ingest() -> IngestionStatusResponse:
    """
    Manually triggers OpenWeatherMap/Open-Meteo ingestion and immediate ML Engine A
    risk scoring without waiting for Celery Beat schedule.
    """
    ingest_res = await weather_ingest_service.ingest_all_wards()
    ml_res = await risk_classifier.compute_and_persist_all_wards()

    return IngestionStatusResponse(
        status="success",
        wards_updated=ingest_res.get("wards_updated", 0),
        total_snapshots_recorded=ingest_res.get("snapshots_created", 0),
        source="openweathermap+open-meteo",
        message=f"Ingestion successful. Evaluated risk for {ml_res.get('wards_evaluated', 0)} wards."
    )
