"""Provenance-preserving event records and append-only operator verification history."""

from datetime import datetime
from typing import Any, List, Optional

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.database import Base


class FloodEvent(Base):
    """A source-attributed event; only operator-confirmed rows are ground-truth candidates."""

    __tablename__ = "flood_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_flood_events_event_id"),
        UniqueConstraint("source_kind", "source_record_id", name="uq_flood_event_source_record"),
        CheckConstraint(
            "source_kind IN ('citizen_report', 'field_observation', 'bmc_record')",
            name="chk_flood_event_source_kind",
        ),
        CheckConstraint(
            "verification_status IN ('operator_confirmed', 'rejected', 'review_required')",
            name="chk_flood_event_verification_status",
        ),
        CheckConstraint(
            "water_depth IS NULL OR water_depth IN ('ankle', 'knee', 'waist', 'submerged')",
            name="chk_flood_event_water_depth",
        ),
        CheckConstraint(
            "water_depth_m IS NULL OR water_depth_m >= 0",
            name="chk_flood_event_water_depth_m",
        ),
        CheckConstraint(
            "location_validation_status IN ('matched', 'outside_wards', 'ambiguous_boundary')",
            name="chk_flood_event_location_validation_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    location: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    location_validation_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("wards.ward_id", ondelete="SET NULL"), nullable=True, index=True
    )
    water_depth: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    water_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    duplicate_of_report_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    location_description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    evidence_image_urls: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="operator_confirmed", index=True
    )
    verified_by: Mapped[str] = mapped_column(String(100), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    official_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verification_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class FloodEventVerificationHistory(Base):
    """Immutable snapshot of each review decision or evidence upload."""

    __tablename__ = "flood_event_verification_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('confirm', 'reject', 'review', 'evidence_added')",
            name="chk_flood_event_history_action",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("citizen_reports.report_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("flood_events.event_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    operator_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(24), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    location_validation_status: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20), ForeignKey("wards.ward_id", ondelete="RESTRICT"), nullable=True
    )
    water_depth: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    water_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    duplicate_of_report_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    evidence_image_urls: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
