"""Response contracts for ward-level predictive flood outlooks."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from backend.services.predictive_features import ForecastHorizon


class WardPredictionResponse(BaseModel):
    ward_id: Optional[str]
    ward_code: str
    ward_name: str
    status: Literal["available", "low_confidence", "unavailable"]
    current_risk_score: Optional[float] = None
    current_risk_category: Optional[str] = None
    current_risk_computed_at: Optional[datetime] = None
    current_risk_model_version: Optional[str] = None
    predicted_risk_score: Optional[float] = Field(
        None, description="Heuristic scenario index (0-1), not a flood probability."
    )
    predicted_probability: None = Field(
        None, description="Unavailable until a model is trained and probability-calibrated."
    )
    risk_category: Optional[Literal["low", "moderate", "high", "critical"]] = None
    horizon: ForecastHorizon
    prediction_timestamp: datetime
    model_version: str
    data_completeness: float = Field(ge=0, le=1)
    contributing_factors: list[str]
    unavailable_reason: Optional[str] = None
    feature_vector: dict[str, Any]
    data_availability: dict[str, bool]
    feature_provenance: dict[str, Any]


class WardPredictionsResponse(BaseModel):
    horizon: ForecastHorizon
    prediction_timestamp: datetime
    model_version: str
    outlook_type: Literal["heuristic_scenario_index"]
    validated_probability_model: bool = False
    supported_horizons: list[ForecastHorizon]
    wards: list[WardPredictionResponse]


class PredictionSummaryResponse(BaseModel):
    horizon: ForecastHorizon
    total_wards: int
    available_wards: int
    low_confidence_wards: int
    high_risk_wards: int
    critical_risk_wards: int
    insufficient_data_wards: int
    increasing_risk_wards: Optional[int] = None
    trend_available: bool = False
    outlook_type: Literal["heuristic_scenario_index"]
    validated_probability_model: bool = False
    supported_horizons: list[ForecastHorizon]
    prediction_timestamp: datetime
