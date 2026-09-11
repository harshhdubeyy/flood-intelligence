"""
SQLAlchemy ORM model for ingested and classified social media intelligence signals.
"""

from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.ward import Ward


class SocialSignal(Base):
    """
    Geotagged or localized social media posts (X/Twitter, Telegram, BMC Helpline 1916).
    Processed by ML Engine C (DistilBERT / IndicBERT / NLP Urgency Classifier).
    """
    __tablename__ = "social_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # 'twitter', 'telegram', 'helpline_1916'
    author_handle: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en")  # 'en', 'mr', 'hi'
    
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    location_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    classification: Mapped[str] = mapped_column(String(30), nullable=False)  # 'evacuation_needed', 'urgent', 'waterlogging', 'noise'
    urgency_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    extracted_landmarks: Mapped[Optional[Any]] = mapped_column(JSONB, nullable=True)
    
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationship to Ward
    ward: Mapped["Ward"] = relationship("Ward")  # noqa: F821
