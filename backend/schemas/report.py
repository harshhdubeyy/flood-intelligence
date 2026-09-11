"""
Pydantic schemas for citizen flood report intake and verification.
"""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ConfigDict


class CitizenReportCreate(BaseModel):
    """Payload for submitting a crowdsourced flood incident."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 Latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 Longitude")
    water_depth: Literal["ankle", "knee", "waist", "submerged"] = Field(
        ...,
        description="Reported categorical water height relative to human landmark"
    )
    description: Optional[str] = Field(None, max_length=500, description="Observer notes or landmark details")
    ward_id: Optional[str] = Field(None, description="Optional pre-identified ward code")


class CitizenReportResponse(BaseModel):
    """API response model for a validated and analyzed citizen report."""
    report_id: str
    ward_id: Optional[str] = None
    latitude: float
    longitude: float
    water_depth: str
    image_url: Optional[str] = None
    cv_verified: bool
    cv_water_depth_m: Optional[float] = None
    cv_confidence: Optional[float] = None
    description: Optional[str] = None
    is_duplicate: bool
    duplicate_of_id: Optional[str] = None
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CitizenReportListResponse(BaseModel):
    """Paginated or filtered list of citizen reports."""
    total: int
    reports: List[CitizenReportResponse]


class ReportVerificationSummary(BaseModel):
    """Aggregate statistics for operator command center triage."""
    total_reports_24h: int
    cv_verified_count: int
    flagged_duplicates: int
    severe_reports: int
