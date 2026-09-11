"""
SQLAlchemy ORM model for citizen flood reports and CV verification.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from backend.models.database import Base


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
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationship to Ward
    ward: Mapped[Optional["Ward"]] = relationship("Ward")  # noqa: F821
