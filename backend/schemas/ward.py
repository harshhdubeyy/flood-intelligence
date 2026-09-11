"""
Pydantic schemas for Ward spatial and operational data.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal

from pydantic import BaseModel, Field, ConfigDict


# ============================================================
# BASIC WARD SCHEMAS
# ============================================================

class WardBase(BaseModel):
    """Base attributes for an administrative ward."""

    ward_id: str = Field(
        ...,
        description="Unique alphanumeric identifier (e.g., MH-BMC-GN)"
    )

    ward_name: str = Field(
        ...,
        description="Human-readable ward name"
    )

    city: str = Field(
        default="Mumbai",
        description="City name"
    )

    area_sqkm: Optional[float] = Field(
        None,
        description="Area in square kilometers"
    )

    population: Optional[int] = Field(
        None,
        description="Estimated population"
    )

    is_coastal: bool = Field(
        default=False,
        description="True if ward borders the coast"
    )

    avg_elevation_m: Optional[float] = Field(
        None,
        description="Average terrain elevation in meters"
    )

    drainage_index: float = Field(
        default=0.5,
        description="Municipal drainage capacity score from 0.0 to 1.0"
    )


class WardResponse(WardBase):
    """API response schema for a single ward summary."""

    id: int = Field(
        ...,
        description="Database serial identifier"
    )

    current_risk_score: Optional[float] = Field(
        default=0.15,
        description="Current flood risk score"
    )

    current_risk_class: Literal[
        "low",
        "medium",
        "high",
        "critical"
    ] = Field(
        default="low",
        description="Categorical risk tier"
    )

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# GEOJSON SCHEMAS
# ============================================================

class WardGeoJSONProperties(BaseModel):
    """Properties attached to each GeoJSON Feature."""

    ward_id: str
    ward_name: str
    city: str

    area_sqkm: Optional[float] = None

    population: Optional[int] = None

    is_coastal: bool = False

    avg_elevation_m: Optional[float] = None

    drainage_index: float = 0.5

    risk_score: float = Field(
        default=0.15,
        description="Normalized flood risk score"
    )

    risk_class: Literal[
        "low",
        "medium",
        "high",
        "critical"
    ] = Field(
        default="low"
    )

    computed_at: datetime


class GeoJSONGeometry(BaseModel):
    """GeoJSON geometry object."""

    type: str

    coordinates: Any


class GeoJSONFeature(BaseModel):
    """Single GeoJSON Feature."""

    type: Literal["Feature"] = "Feature"

    id: str

    geometry: GeoJSONGeometry

    properties: WardGeoJSONProperties


class GeoJSONFeatureCollection(BaseModel):
    """RFC 7946 GeoJSON FeatureCollection."""

    type: Literal["FeatureCollection"] = "FeatureCollection"

    features: List[GeoJSONFeature]


# ============================================================
# RISK HISTORY SCHEMAS
# ============================================================

class WardRiskItem(BaseModel):
    """Single historical flood risk measurement."""

    risk_score: float

    risk_class: Literal[
        "low",
        "medium",
        "high",
        "critical"
    ]

    model_version: Optional[str] = None

    computed_at: datetime

    inputs_json: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class WardRiskHistoryResponse(BaseModel):
    """24-hour flood risk history response."""

    ward_id: str

    ward_name: str

    current_score: float

    current_class: Literal[
        "low",
        "medium",
        "high",
        "critical"
    ]

    history_24h: List[WardRiskItem]
