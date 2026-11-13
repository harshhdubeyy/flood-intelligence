"""
Pydantic schemas for citizen flood report intake and verification.
"""

from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


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
    operator_verification_status: str = "pending"
    submitted_at: datetime
    nlp_analysis: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class CitizenReportListResponse(BaseModel):
    """Paginated or filtered list of citizen reports."""
    total: int
    reports: List[CitizenReportResponse]


class ReportVerificationSummary(BaseModel):
    """Aggregate statistics for operator command center triage."""
    total_reports: int
    total_reports_24h: int
    cv_verified_count: int
    flagged_duplicates: int
    severe_reports: int
    operator_pending: int = 0
    operator_confirmed: int = 0
    operator_rejected: int = 0
    operator_review_required: int = 0
    ward_wise_counts: Dict[str, int] = {}
    water_depth_distribution: Dict[str, int] = {}


class ReportDetailResponse(BaseModel):
    """Detailed response for an individual citizen report."""
    report_id: str
    ward_id: Optional[str] = None
    latitude: float
    longitude: float
    water_depth: str
    image_url: Optional[str] = None
    cv_verified: bool
    cv_water_depth_m: Optional[float] = None
    cv_confidence: Optional[float] = None
    cv_detected_objects: Optional[List[dict]] = None
    cv_water_detected: Optional[bool] = None
    cv_reason: Optional[str] = None
    description: Optional[str] = None
    is_duplicate: bool
    duplicate_of_id: Optional[str] = None
    operator_verification_status: str = "pending"
    location_validation_status: Optional[str] = None
    submitted_at: datetime
    nlp_analysis: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class ReportVerificationRequest(BaseModel):
    """Operator decision and any corrected event details."""

    action: Literal["confirm", "reject", "review"]
    reason: Optional[str] = Field(None, max_length=2000)
    event_timestamp: Optional[datetime] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False)
    longitude: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False)
    water_depth: Optional[Literal["ankle", "knee", "waist", "submerged"]] = None
    water_depth_m: Optional[float] = Field(None, ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_decision(self) -> "ReportVerificationRequest":
        if self.action in ("reject", "review") and not (self.reason and self.reason.strip()):
            raise ValueError("A reason is required when rejecting or flagging a report.")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together.")
        if self.event_timestamp is not None and self.event_timestamp.tzinfo is None:
            raise ValueError("event_timestamp must include a timezone.")
        return self


class OperatorReportQueueResponse(BaseModel):
    total: int
    reports: List[ReportDetailResponse]


class OperatorIdentityResponse(BaseModel):
    operator_id: str


class FloodEventResponse(BaseModel):
    event_id: str
    source_kind: str
    source_record_id: Optional[str] = None
    source_url: Optional[str] = None
    event_timestamp: datetime
    latitude: float
    longitude: float
    location_validation_status: Optional[str] = None
    ward_id: Optional[str] = None
    water_depth: Optional[str] = None
    water_depth_m: Optional[float] = None
    is_duplicate: bool = False
    duplicate_of_report_id: Optional[str] = None
    location_description: Optional[str] = None
    evidence_image_urls: List[str] = Field(default_factory=list)
    verification_status: str
    verified_by: str
    verified_at: datetime
    official_confirmation: bool
    verification_reason: Optional[str] = None


class FloodEventVerificationHistoryResponse(BaseModel):
    id: int
    report_id: str
    event_id: Optional[str] = None
    operator_id: str
    action: str
    previous_status: str
    new_status: str
    reason: Optional[str] = None
    event_timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_validation_status: Optional[str] = None
    ward_id: Optional[str] = None
    water_depth: Optional[str] = None
    water_depth_m: Optional[float] = None
    is_duplicate: bool = False
    duplicate_of_report_id: Optional[str] = None
    evidence_image_urls: List[str] = Field(default_factory=list)
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportVerificationResponse(BaseModel):
    report_id: str
    operator_verification_status: str
    event_id: Optional[str] = None
    verification_history_id: int
    official_confirmation: bool = False


class FloodEventListResponse(BaseModel):
    total: int
    events: List[FloodEventResponse]
