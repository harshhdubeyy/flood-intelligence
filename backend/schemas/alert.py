"""
Pydantic schemas for multi-channel emergency alert authoring, CAP v1.2,
citizen subscriptions, PostGIS 5 km recipient targeting, and delivery analytics.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


class AlertCreate(BaseModel):
    """Payload for creating an emergency flood alert broadcast."""
    ward_id: Optional[str] = Field(None, description="Target administrative ward code (e.g., BMC-A, BMC-HW)")
    center_latitude: Optional[float] = Field(
        None,
        ge=18.5,
        le=19.5,
        description="Target center latitude in Mumbai region",
    )
    center_longitude: Optional[float] = Field(
        None,
        ge=72.5,
        le=73.5,
        description="Target center longitude in Mumbai region",
    )
    radius_km: float = Field(
        default=5.0,
        gt=0.1,
        le=50.0,
        description="Target circular broadcast radius in km (default 5 km)",
    )
    severity: Literal["watch", "warning", "critical"] = Field(
        ...,
        description="Alert severity tier mapped to OASIS CAP severity guidelines",
    )
    channel: Literal["cap", "whatsapp", "push", "all"] = Field(
        default="all",
        description="Distribution channel",
    )
    headline: str = Field(..., min_length=5, max_length=200, description="Short bulletin headline")
    instruction: Optional[str] = Field(None, max_length=500, description="Recommended citizen protective action")
    expires_in_hours: float = Field(
        default=6.0,
        gt=0.25,
        le=72.0,
        description="Alert validity window in hours before expiration",
    )

    @field_validator("radius_km")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Radius must be greater than 0 km")
        return round(v, 2)


class MultilingualText(BaseModel):
    """Localized alert content for Mumbai demographics."""
    en: str
    mr: str  # Marathi (Official state language)
    hi: str  # Hindi


class AlertResponse(BaseModel):
    """API response model for an alert bulletin."""
    alert_id: str
    ward_id: Optional[str] = None
    severity: str
    channel: str
    headline: str
    message_text: Optional[str] = None
    status: str = "dispatched"
    radius_km: float = 5.0
    center_latitude: Optional[float] = None
    center_longitude: Optional[float] = None
    cap_xml: Optional[str] = None
    recipients_count: int = 0
    language_translations: Optional[Dict[str, Any]] = None
    delivery_summary: Optional[Dict[str, Any]] = None
    dispatched_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertDetailResponse(AlertResponse):
    """Detailed view including authorization, cancellation, and targeting metrics."""
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by: Optional[str] = None
    cancellation_reason: Optional[str] = None


class AlertListResponse(BaseModel):
    """Chronological list of issued emergency bulletins."""
    total: int
    alerts: List[AlertResponse]


# ---------------------------------------------------------------------------
# Citizen Subscriptions & Consent
# ---------------------------------------------------------------------------

class WebPushSubscriptionKeys(BaseModel):
    p256dh: str = Field(..., min_length=10, description="Public encryption key")
    auth: str = Field(..., min_length=6, description="Authentication secret")


class CitizenSubscriptionCreate(BaseModel):
    """Registration request for browser push notifications with explicit consent."""
    endpoint: str = Field(..., min_length=10, description="Push service delivery endpoint URL")
    keys: WebPushSubscriptionKeys = Field(..., description="p256dh and auth cryptographic keys")
    device_type: Literal["web", "android", "ios"] = "web"
    device_fingerprint: Optional[str] = Field(None, max_length=128)
    user_agent: Optional[str] = Field(None, max_length=512)

    notification_consent: bool = Field(
        ...,
        description="Explicit user consent to receive emergency flood bulletins",
    )
    location_consent: bool = Field(
        default=False,
        description="Explicit consent to store coarse device location for 5 km proximity alerts",
    )
    latitude: Optional[float] = Field(None, ge=18.5, le=19.5, description="Mumbai area latitude")
    longitude: Optional[float] = Field(None, ge=72.5, le=73.5, description="Mumbai area longitude")
    accuracy_meters: Optional[float] = Field(None, ge=0, le=50000)
    ward_id: Optional[str] = Field(None, max_length=32)

    preferred_language: Literal["en", "mr", "hi"] = "en"
    min_severity: Literal["watch", "warning", "critical"] = "watch"

    @field_validator("notification_consent")
    @classmethod
    def validate_notif_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Explicit notification consent is required to register subscription")
        return v


class WebPushSubscription(BaseModel):
    """Legacy compatibility schema for VAPID browser Web Push registration."""
    endpoint: str
    keys: Dict[str, str] = Field(..., description="p256dh and auth keys")
    ward_id: Optional[str] = Field(None, description="Ward to filter localized alerts")


class CitizenSubscriptionResponse(BaseModel):
    """Response returned after citizen subscription registration or lookup."""
    subscription_id: str
    device_type: str
    notification_consent: bool
    location_consent: bool
    preferred_language: str
    min_severity: str
    is_active: bool
    has_location: bool
    ward_id: Optional[str] = None
    location_updated_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionPreferencesUpdate(BaseModel):
    """Citizen preferences update (language, severity threshold, home ward)."""
    preferred_language: Optional[Literal["en", "mr", "hi"]] = None
    min_severity: Optional[Literal["watch", "warning", "critical"]] = None
    ward_id: Optional[str] = None


class LocationConsentUpdateRequest(BaseModel):
    """Consent and coordinates update from browser geolocation API."""
    location_consent: bool = Field(..., description="Allow or revoke coarse location storage")
    latitude: Optional[float] = Field(None, ge=18.5, le=19.5)
    longitude: Optional[float] = Field(None, ge=72.5, le=73.5)
    accuracy_meters: Optional[float] = Field(None, ge=0, le=50000)


class SubscriptionRevokeRequest(BaseModel):
    """Explicit opt-out / unsubscribe request."""
    reason: Optional[str] = Field(None, max_length=200)


# ---------------------------------------------------------------------------
# Recipient Preview & Targeting
# ---------------------------------------------------------------------------

class RecipientPreviewRequest(BaseModel):
    """Operator request to preview eligible recipient count before broadcasting."""
    center_latitude: Optional[float] = Field(None, ge=18.5, le=19.5)
    center_longitude: Optional[float] = Field(None, ge=72.5, le=73.5)
    ward_id: Optional[str] = None
    radius_km: float = Field(default=5.0, gt=0.1, le=50.0)
    severity: Literal["watch", "warning", "critical"] = "warning"
    freshness_hours: Optional[int] = Field(None, ge=1, le=168)


class RecipientPreviewResponse(BaseModel):
    """Preview analytics for geographic radius targeting."""
    eligible_subscribers: int
    radius_km: float
    center: Dict[str, float]
    severity: str
    freshness_threshold_hours: int
    languages: Dict[str, int]
    dispatch_enabled: bool


# ---------------------------------------------------------------------------
# Alert Management & Delivery Tracking
# ---------------------------------------------------------------------------

class AlertApprovalRequest(BaseModel):
    """Operator approval for dispatching an alert."""
    notes: Optional[str] = Field(None, max_length=300)


class AlertCancelRequest(BaseModel):
    """Operator cancellation of an active or pending alert."""
    reason: str = Field(..., min_length=3, max_length=300)


class DeliveryAttemptItem(BaseModel):
    subscription_id: str
    channel: str
    status: str
    attempts: int
    last_attempt_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AlertAnalyticsResponse(BaseModel):
    """Comprehensive delivery metrics and audit trail for an alert."""
    alert_id: str
    status: str
    radius_km: float
    recipients_count: int
    delivery_summary: Optional[Dict[str, Any]] = None
    deliveries: List[DeliveryAttemptItem]
    audit_logs: List[Dict[str, Any]]


# Aliases for backwards compatibility / alternate naming
SubscriptionLocationUpdate = LocationConsentUpdateRequest
AlertDispatchRequest = AlertApprovalRequest
