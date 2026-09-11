"""
SQLAlchemy ORM model for Mumbai Municipal Administrative Wards.
"""

from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from backend.models.database import Base


class Ward(Base):
    """
    Represents a Municipal Administrative Ward in Mumbai (e.g. MH-BMC-GN / Dharavi).
    Stores spatial boundaries as PostGIS MultiPolygon in SRID 4326.
    """
    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ward_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    ward_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(50), default="Mumbai", server_default="Mumbai")
    geom: Mapped[Geometry] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326),
        nullable=False
    )
    area_sqkm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    population: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_coastal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    avg_elevation_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    drainage_index: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")

    # Relationships
    risk_scores: Mapped[List["WardRiskScore"]] = relationship(  # noqa: F821
        "WardRiskScore",
        back_populates="ward",
        cascade="all, delete-orphan",
        order_by="desc(WardRiskScore.computed_at)"
    )