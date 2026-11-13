"""
SQLAlchemy ORM model for citizen flood reports and CV verification.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from backend.models.database import Base

if TYPE_CHECKING:
    from backend.models.ward import Ward
from sqlalchemy.dialects.postgresql import JSONB


class CitizenReport(Base):
    """
    Crowdsourced flood incident report submitted by citizens or field volunteers.
    Processed by ML Engine B (Computer Vision depth estimator & verification).
    """
    __tablename__ = "citizen_reports"
    __table_args__ = (
        CheckConstraint(
            "water_depth IN ('ankle', 'knee', 'waist', 'submerged')",
            name="chk_citizen_reports_water_depth"
        ),
        CheckConstraint(
            "operator_verification_status IN ('pending', 'confirmed', 'rejected', 'review_required', 'resolved', 'expired')",
            name="chk_citizen_report_operator_verification_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    location: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=False
    )
    water_depth: Mapped[str] = mapped_column(String(20), nullable=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    cv_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    cv_water_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cv_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    duplicate_of_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    operator_verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default="pending", index=True
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationship to Ward
    ward: Mapped[Optional["Ward"]] = relationship("Ward")  # noqa: F821
    nlp_analysis: Mapped[Optional["CitizenReportNLPAnalysis"]] = relationship(
        "CitizenReportNLPAnalysis", back_populates="report", uselist=False, cascade="all, delete-orphan"
    )


class CitizenReportNLPAnalysis(Base):
    """
    Extracted NLP derived features for crowdsourced citizen flood reports.
    Preserves separation between citizen-reported depth, CV depth, and NLP depth.
    """
    __tablename__ = "citizen_report_nlp_analysis"
    __table_args__ = (
        CheckConstraint(
            "classification IN ('waterlogging', 'urgent', 'evacuation_needed', 'noise', 'spam', 'general_weather')",
            name="chk_report_nlp_classification",
        ),
        CheckConstraint(
            "detected_language IN ('en', 'mr', 'hi', 'und')",
            name="chk_report_nlp_language",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_report_nlp_confidence",
        ),
        CheckConstraint(
            "urgency_score >= 0.0 AND urgency_score <= 1.0",
            name="chk_report_nlp_urgency",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("citizen_reports.report_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    model_version: Mapped[str] = mapped_column(String(48), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    urgency_score: Mapped[float] = mapped_column(Float, nullable=False)
    is_flood_related: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_waterlogging: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    detected_language: Mapped[str] = mapped_column(String(12), default="en", server_default="en")
    extracted_depth_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extracted_landmarks: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    matched_keywords: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    provenance: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    report: Mapped["CitizenReport"] = relationship("CitizenReport", back_populates="nlp_analysis")
