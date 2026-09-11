"""
SQLAlchemy ORM model for Ward Risk Scores.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base


class WardRiskScore(Base):
    """
    Historical and real-time risk scores evaluated for a specific ward.
    Updated every 15 minutes by the ML Risk Classifier (Engine A).
    """
    __tablename__ = "ward_risk_scores"
    __table_args__ = (
        CheckConstraint("risk_score >= 0.0 AND risk_score <= 1.0", name="chk_ward_risk_score_range"),
        CheckConstraint("risk_class IN ('low', 'medium', 'high', 'critical')", name="chk_ward_risk_class"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ward_id: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_class: Mapped[str] = mapped_column(String(20), nullable=False)
    model_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    inputs_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ward: Mapped["Ward"] = relationship("Ward", back_populates="risk_scores")  # noqa: F821
