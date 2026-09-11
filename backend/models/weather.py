"""
SQLAlchemy ORM model for real-time and historical weather snapshots.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.database import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.ward import Ward


class WeatherSnapshot(Base):
    """
    Environmental telemetry captured per ward from OpenWeatherMap and Open-Meteo.
    Polled every 10-30 minutes and used as input to Engine A (ML Risk Classifier).
    """
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # 'openweathermap' | 'open-meteo'
    rainfall_1h_mm: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    rainfall_3h_mm: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    rainfall_24h_mm: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    wind_speed_kmh: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    humidity_pct: Mapped[Optional[float]] = mapped_column(Float, default=0.0)
    tide_height_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationship to Ward
    ward: Mapped["Ward"] = relationship("Ward")  # noqa: F821
