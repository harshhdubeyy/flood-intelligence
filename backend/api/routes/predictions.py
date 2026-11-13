"""Ward-level predictive flood outlook endpoints."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.schemas.prediction import (
    PredictionSummaryResponse,
    WardPredictionResponse,
    WardPredictionsResponse,
)
from backend.services.predictive_features import (
    FORECAST_HORIZONS,
    ForecastHorizon,
    PredictiveFeatureService,
    normalize_ward_code,
    prediction_from_features,
)

router = APIRouter(prefix="/predictions", tags=["Predictive Intelligence"])


async def _build_response(
    db: AsyncSession,
    horizon: ForecastHorizon,
) -> WardPredictionsResponse:
    now = datetime.now(timezone.utc)
    vectors = await PredictiveFeatureService(db).build_citywide_features(now)
    predictions = [prediction_from_features(vector, horizon, now) for vector in vectors]
    supported_horizons = [
        candidate
        for candidate in FORECAST_HORIZONS
        if any(
            vector.features.get(f"forecast_rainfall_{candidate}_mm") is not None
            for vector in vectors
        )
    ]
    return WardPredictionsResponse(
        horizon=horizon,
        prediction_timestamp=now,
        model_version="heuristic-outlook-v1",
        outlook_type="heuristic_scenario_index",
        supported_horizons=supported_horizons,
        wards=predictions,
    )


@router.get(
    "/wards",
    response_model=WardPredictionsResponse,
    summary="Retrieve heuristic flood outlooks for all Mumbai wards",
)
async def get_ward_predictions(
    horizon: Annotated[ForecastHorizon, Query()] = "6h",
    db: AsyncSession = Depends(get_db),
) -> WardPredictionsResponse:
    return await _build_response(db, horizon)


@router.get(
    "/wards/{ward_id}",
    response_model=WardPredictionResponse,
    summary="Retrieve the heuristic flood outlook for one Mumbai ward",
)
async def get_ward_prediction(
    ward_id: str,
    horizon: Annotated[ForecastHorizon, Query()] = "6h",
    db: AsyncSession = Depends(get_db),
) -> WardPredictionResponse:
    response = await _build_response(db, horizon)
    ward = next(
        (
            item for item in response.wards
            if item.ward_id == ward_id
            or normalize_ward_code(item.ward_code) == normalize_ward_code(ward_id)
        ),
        None,
    )
    if ward is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ward '{ward_id}' was not found.",
        )
    return ward


@router.get(
    "/summary",
    response_model=PredictionSummaryResponse,
    summary="Retrieve city-wide predictive flood outlook statistics",
)
async def get_prediction_summary(
    horizon: Annotated[ForecastHorizon, Query()] = "6h",
    db: AsyncSession = Depends(get_db),
) -> PredictionSummaryResponse:
    response = await _build_response(db, horizon)
    scored = [ward for ward in response.wards if ward.predicted_risk_score is not None]
    return PredictionSummaryResponse(
        horizon=horizon,
        total_wards=len(response.wards),
        available_wards=sum(ward.status == "available" for ward in scored),
        low_confidence_wards=sum(ward.status == "low_confidence" for ward in scored),
        high_risk_wards=sum(ward.risk_category == "high" for ward in scored),
        critical_risk_wards=sum(ward.risk_category == "critical" for ward in scored),
        insufficient_data_wards=len(response.wards) - len(scored),
        increasing_risk_wards=None,
        trend_available=False,
        outlook_type="heuristic_scenario_index",
        supported_horizons=response.supported_horizons,
        prediction_timestamp=response.prediction_timestamp,
    )
