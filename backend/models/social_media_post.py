"""Original public social-media records kept separate from flood ground truth."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from backend.models.database import Base


class SocialMediaPost(Base):
    """Source-preserving record of a publicly accessible platform post."""

    __tablename__ = "social_media_posts"
    __table_args__ = (
        UniqueConstraint(
            "platform", "external_post_id", name="uq_social_media_posts_platform_external"
        ),
        CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL AND "
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="chk_social_media_post_coordinate_pair",
        ),
        CheckConstraint(
            "geolocation_confidence IS NULL OR geolocation_confidence BETWEEN 0 AND 1",
            name="chk_social_media_post_geolocation_confidence",
        ),
        CheckConstraint(
            "source_status IN ('unverified', 'current', 'pending_compliance', "
            "'unavailable', 'expired', 'deleted')",
            name="chk_social_media_post_source_status",
        ),
        Index("ix_social_media_posts_posted_at", "posted_at"),
        Index("ix_social_media_posts_collected_at", "collected_at"),
        Index("ix_social_media_posts_ward_id", "ward_id"),
        Index("ix_social_media_posts_processing_status", "processing_status"),
        Index("ix_social_media_posts_expires_at", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    external_post_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    original_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    location_text: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("wards.ward_id", ondelete="SET NULL"), nullable=True
    )
    geolocation_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ward_assignment_provenance: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    matched_keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    media_references: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="collected", server_default="collected"
    )
    source_provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unverified", server_default="unverified"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_reconcile_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reconcile_attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SocialPostDerivedArtifact(Base):
    """Optional future derived data, deleted with its source post."""

    __tablename__ = "social_post_derived_artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('nlp', 'cv', 'location', 'summary', 'search_index')",
            name="chk_social_post_derived_artifact_type",
        ),
        Index("ix_social_post_derived_artifacts_post_id", "social_post_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    social_post_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("social_media_posts.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(24), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SocialComplianceTombstone(Base):
    """Non-reversible source-key digest used to suppress re-ingestion after removal."""

    __tablename__ = "social_compliance_tombstones"
    __table_args__ = (
        UniqueConstraint(
            "platform", "source_id_digest", name="uq_social_tombstone_platform_digest"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(24), nullable=False)
    source_id_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SocialComplianceOperation(Base):
    """Immutable attempt record; retries append a new row under the same request ID."""

    __tablename__ = "social_compliance_operations"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "attempt_number",
            name="uq_social_compliance_operation_attempt",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'retryable', 'failed', 'dry_run')",
            name="chk_social_compliance_operation_status",
        ),
        Index("ix_social_compliance_operations_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    platform: Mapped[str] = mapped_column(String(24), nullable=False)
    post_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("social_media_posts.id", ondelete="RESTRICT"), nullable=True
    )
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    outcome: Mapped[str] = mapped_column(String(48), nullable=False)
    event_id_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SocialCollectionRun(Base):
    """Sanitized outcome and timing metadata for one provider collection attempt."""

    __tablename__ = "social_collection_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'error', 'not_configured', 'disabled')",
            name="chk_social_collection_run_status",
        ),
        Index("ix_social_collection_runs_platform_completed", "platform", "completed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(24), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    collected_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
