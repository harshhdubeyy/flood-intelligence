# Placeholder for backend/models/alert.py
"""
SQLAlchemy ORM model for dispatched emergency alerts and audit tracking.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base


class AlertDispatched(Base):
    """
    Emergency alerts published via OASIS CAP v1.2, WhatsApp, Web Push, and SMS.
    Tracks multilingual message content, target polygon geometry, and dispatch telemetry.
    """
    __tablename__ = "alerts_dispatched"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('warning', 'watch', 'critical')",
            name="chk_alerts_severity"
        ),
        CheckConstraint(
            "channel IN ('cap', 'whatsapp', 'push', 'all')",
            name="chk_alerts_channel"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    cap_xml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    language_translations: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationship to Ward
    ward: Mapped[Optional["Ward"]] = relationship("Ward")  # noqa: F821
