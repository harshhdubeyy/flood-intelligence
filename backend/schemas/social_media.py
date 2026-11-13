"""Validated API schemas for sourced social-media collection records."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SocialMediaPostResponse(BaseModel):
    id: int
    platform: str
    external_post_id: Optional[str]
    original_url: Optional[str]
    text_content: Optional[str]
    posted_at: Optional[datetime]
    collected_at: datetime
    location_text: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    ward_id: Optional[str]
    geolocation_confidence: Optional[float]
    ward_assignment_provenance: Optional[str]
    matched_keywords: list[str]
    media_references: list[dict[str, Any]]
    processing_status: str
    source_provenance: dict[str, Any]
    source_status: str
    expires_at: Optional[datetime]
    last_verified_at: Optional[datetime]
    next_reconcile_at: Optional[datetime]
    nlp_analysis: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class SocialMediaPostPage(BaseModel):
    total: int
    limit: int
    offset: int
    posts: list[SocialMediaPostResponse]


class SocialProviderStatus(BaseModel):
    platform: str
    state: str
    configured: bool
    last_success_at: Optional[datetime]
    lifecycle_policy_ready: bool = False


class SocialStatusResponse(BaseModel):
    providers: list[SocialProviderStatus]
    latest_success_at: Optional[datetime]


class SocialSummaryResponse(BaseModel):
    total_posts: int
    posts_last_24h: int
    platform_breakdown: dict[str, int]
    latest_collected_at: Optional[datetime]


class SocialKeywordConfiguration(BaseModel):
    categories: dict[str, list[str]] = Field(default_factory=dict)
    mumbai_locations: list[str] = Field(default_factory=list)


class SocialTakedownRequest(BaseModel):
    post_id: int = Field(gt=0)


class SocialProviderComplianceEvent(BaseModel):
    platform: Literal["reddit", "x"]
    external_post_id: str = Field(min_length=1, max_length=256)
    action: Literal[
        "delete",
        "remove",
        "drop",
        "withheld",
        "scrub_geo",
        "rehydrate",
        "tweet_edit",
        "undrop",
    ]
    event_id: Optional[str] = Field(default=None, max_length=256)

    def model_post_init(self, __context: Any) -> None:
        if self.platform == "reddit" and self.action not in {"delete", "remove"}:
            raise ValueError("Unsupported Reddit compliance action.")


class SocialComplianceOperationResponse(BaseModel):
    request_id: UUID
    attempt_number: int
    operation_type: str
    platform: str
    post_id: Optional[int]
    trigger_source: str
    status: str
    error_code: Optional[str]
    outcome: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
