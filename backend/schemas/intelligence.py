"""
Pydantic schemas for Citizen Report Intelligence Engine.
Provides ward-level analytics, reliability scoring, hotspot detection,
and citizen flood intelligence scores derived from citizen-submitted reports.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


# -------------------------------------------------------
# WARD-WISE INCIDENT ANALYTICS
# -------------------------------------------------------

class WardIncidentAnalytics(BaseModel):
    """Per-ward citizen flood report analytics."""
    ward_id: str = Field(..., description="Unique ward identifier")
    ward_name: str = Field(..., description="Human-readable ward name")
    total_reports: int = Field(..., description="Total citizen reports for this ward")
    reports_last_1h: int = Field(..., description="Reports in the last 1 hour")
    reports_last_3h: int = Field(..., description="Reports in the last 3 hours")
    reports_last_24h: int = Field(..., description="Reports in the last 24 hours")
    cv_verified_count: int = Field(..., description="CV-verified reports")
    unverified_count: int = Field(..., description="Unverified reports")
    duplicate_count: int = Field(..., description="Duplicate reports")
    severe_count: int = Field(..., description="Severe flood reports (waist/submerged)")
    avg_severity: float = Field(..., ge=0.0, le=1.0, description="Average reported flood severity (0-1)")
    latest_incident: Optional[datetime] = Field(None, description="Most recent incident timestamp")

    model_config = ConfigDict(from_attributes=True)


class WardIntelligenceScore(BaseModel):
    """Normalized citizen flood intelligence score for a ward (0-1)."""
    ward_id: str = Field(..., description="Unique ward identifier")
    ward_name: str = Field(..., description="Human-readable ward name")
    intelligence_score: float = Field(..., ge=0.0, le=1.0, description="Citizen flood intelligence score (0-1)")
    intelligence_class: Literal["minimal", "low", "moderate", "elevated", "critical"] = Field(
        ..., description="Qualitative intelligence classification"
    )
    severity_factor: float = Field(..., ge=0.0, le=1.0, description="Severity component weight")
    recency_factor: float = Field(..., ge=0.0, le=1.0, description="Recency component weight")
    verification_factor: float = Field(..., ge=0.0, le=1.0, description="CV verification component weight")
    clustering_factor: float = Field(..., ge=0.0, le=1.0, description="Geographic clustering component weight")
    volume_factor: float = Field(..., ge=0.0, le=1.0, description="Report volume component weight")
    report_count: int = Field(..., description="Total non-duplicate reports considered")
    cv_verified_count: int = Field(..., description="CV-verified reports considered")
    duplicate_count: int = Field(..., description="Duplicate reports (suppressed from scoring)")
    latest_incident: Optional[datetime] = Field(None, description="Most recent incident timestamp")
    model_version: str = Field(..., description="Intelligence model version")
    avg_reliability: float = Field(..., ge=0.0, le=1.0, description="Average report reliability score")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------
# REPORT RELIABILITY SCORING
# -------------------------------------------------------

class ReportReliability(BaseModel):
    """Reliability score for an individual citizen report (0-1)."""
    report_id: str = Field(..., description="Unique report identifier")
    reliability_score: float = Field(..., ge=0.0, le=1.0, description="Normalized reliability score (0-1)")
    cv_verified: bool = Field(..., description="Whether CV verification passed")
    cv_confidence: Optional[float] = Field(None, description="CV confidence score if available")
    is_duplicate: bool = Field(..., description="Whether this is a duplicate report")
    has_image: bool = Field(..., description="Whether a photograph was submitted")
    has_description: bool = Field(..., description="Whether a text description was provided")
    score_breakdown: Dict[str, float] = Field(..., description="Component scores used in calculation")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------
# FLOOD HOTSPOT DETECTION
# -------------------------------------------------------

class FloodHotspot(BaseModel):
    """Geographic cluster of citizen flood reports."""
    hotspot_id: str = Field(..., description="Unique hotspot identifier")
    center_latitude: float = Field(..., description="Cluster center latitude")
    center_longitude: float = Field(..., description="Cluster center longitude")
    radius_meters: float = Field(..., description="Cluster radius in meters")
    report_count: int = Field(..., description="Number of non-duplicate reports in cluster")
    cv_verified_count: int = Field(..., description="CV-verified reports in cluster")
    severe_count: int = Field(..., description="Severe reports (waist/submerged) in cluster")
    avg_severity: float = Field(..., ge=0.0, le=1.0, description="Average severity in cluster")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Hotspot confidence score (0-1)")
    latest_incident: Optional[datetime] = Field(None, description="Most recent incident in cluster")
    ward_ids: List[str] = Field(default_factory=list, description="Wards intersecting this hotspot")

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------
# COMBINED RESPONSES
# -------------------------------------------------------

class WardIntelligenceResponse(BaseModel):
    """Combined analytics and intelligence score for a ward."""
    analytics: WardIncidentAnalytics
    intelligence: Optional[WardIntelligenceScore] = Field(
        None, description="Citizen flood intelligence score (None for wards without reports)"
    )
    reliability_summary: Dict[str, Any] = Field(..., description="Aggregate reliability statistics")

    model_config = ConfigDict(from_attributes=True)


class IntelligenceSummary(BaseModel):
    """Overall citizen flood intelligence summary across all wards."""
    total_reports: int = Field(..., description="Total citizen reports across all wards")
    reports_last_24h: int = Field(..., description="Reports in the last 24 hours")
    cv_verified_count: int = Field(..., description="Total CV-verified reports")
    duplicate_count: int = Field(..., description="Total duplicate reports")
    severe_count: int = Field(..., description="Total severe reports")
    avg_intelligence_score: float = Field(..., ge=0.0, le=1.0, description="Average ward intelligence score")
    critical_wards: List[str] = Field(default_factory=list, description="Ward IDs with critical intelligence")
    hotspot_count: int = Field(..., description="Number of active flood hotspots")
    wards_with_reports: int = Field(..., description="Number of wards with at least one report")
    model_version: str = Field(..., description="Intelligence model version")

    model_config = ConfigDict(from_attributes=True)