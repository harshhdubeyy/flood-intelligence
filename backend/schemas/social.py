"""
Pydantic schemas for social media intelligence signals and NLP triage.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class SocialSignalCreate(BaseModel):
    """Payload for manually injecting or streaming a social post."""
    source: Literal["twitter", "telegram", "helpline_1916", "citizen_app"] = Field(
        default="twitter",
        description="Source channel of intelligence"
    )
    author_handle: Optional[str] = Field(None, max_length=60, description="Author username or masked contact")
    content_text: str = Field(..., min_length=3, max_length=1000, description="Raw social post text")
    language: Optional[str] = Field(default="auto", description="en, mr, hi, or auto-detect")
    ward_id: Optional[str] = Field(None, description="Pre-identified ward ID or auto-geocoded")
    location_name: Optional[str] = Field(None, description="Explicit landmark name if known")
    posted_at: Optional[datetime] = Field(None, description="Original timestamp of publication")


class SocialSignalResponse(BaseModel):
    """API response model for an evaluated social post."""
    signal_id: str
    source: str
    author_handle: Optional[str] = None
    content_text: str
    language: str
    ward_id: Optional[str] = None
    location_name: Optional[str] = None
    classification: str
    urgency_score: float
    confidence: float
    extracted_landmarks: Optional[List[str]] = None
    posted_at: datetime
    ingested_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SocialSignalListResponse(BaseModel):
    """List of ingested social media signals."""
    total: int
    signals: List[SocialSignalResponse]


class HotspotKeyword(BaseModel):
    """Top recurring Mumbai flood location mention."""
    landmark: str
    ward_id: Optional[str]
    count: int
    avg_urgency: float


class SocialSummaryResponse(BaseModel):
    """Aggregate statistics for social situational awareness."""
    total_signals_24h: int
    urgent_signals_count: int
    evacuation_mentions_count: int
    top_hotspots: List[HotspotKeyword]
    classification_distribution: Dict[str, int]
