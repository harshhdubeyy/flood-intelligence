"""
Pydantic schemas for multi-channel emergency alert authoring, CAP v1.2, and dispatch.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class AlertCreate(BaseModel):
    """Payload for triggering an emergency alert broadcast."""
    ward_id: str = Field(..., description="Target administrative ward code (e.g., MH-BMC-GN)")
    severity: Literal["watch", "warning", "critical"] = Field(
        ...,
        description="Alert severity tier mapped to OASIS CAP severity guidelines"
    )
    channel: Literal["cap", "whatsapp", "push", "all"] = Field(
        default="all",
        description="Distribution channel"
    )
    headline: str = Field(..., max_length=200, description="Short bulletin headline")
    instruction: Optional[str] = Field(None, description="Recommended citizen protective action")


class MultilingualText(BaseModel):
    """Localized alert content for Mumbai demographics."""
    en: str
    mr: str  # Marathi (Official state language)
    hi: str  # Hindi


class AlertResponse(BaseModel):
    """API response model for a dispatched alert bulletin."""
    alert_id: str
    ward_id: Optional[str] = None
    severity: str
    channel: str
    headline: str
    message_text: str
    cap_xml: Optional[str] = None
    recipients_count: int
    language_translations: Optional[Dict[str, Any]] = None
    dispatched_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertListResponse(BaseModel):
    """Chronological list of issued emergency bulletins."""
    total: int
    alerts: List[AlertResponse]


class WebPushSubscription(BaseModel):
    """VAPID browser Web Push subscription registration."""
    endpoint: str
    keys: Dict[str, str] = Field(..., description="p256dh and auth keys")
    ward_id: Optional[str] = Field(None, description="Ward to filter localized alerts")
