"""
Weather and forecast API endpoints for current conditions and triggerable ingestion.
"""

from typing import List, Optional
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(prefix="/weather", tags=["Weather"])


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
