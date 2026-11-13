"""
SQLAlchemy ORM models for the Citizen Notification System, 5 km Geographic Targeting,
Alert Lifecycle, Web Push Deliveries, and Operator Audit Logs.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    func,
    CheckConstraint,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from geoalchemy2 import Geometry

from backend.models.database import Base

if TYPE_CHECKING:
    from backend.models.ward import Ward


class AlertDispatched(Base):
    """
    Emergency alerts published via OASIS CAP v1.2, Web Push, and municipal channels.
    Tracks multilingual message content, PostGIS geographic center, configurable 5 km radius,
    approval gates, and dispatch telemetry.
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
        CheckConstraint(
            "status IN ('draft', 'pending_approval', 'approved', 'queued', 'dispatching', 'completed', 'partially_failed', 'failed', 'cancelled', 'expired')",
            name="chk_alerts_status"
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
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", server_default="completed", index=True)
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    center_location: Mapped[Optional[Geometry]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True
    )
    radius_km: Mapped[float] = mapped_column(Float, nullable=False, default=5.0, server_default="5.0")
    cap_xml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    language_translations: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    delivery_summary: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    ward: Mapped[Optional["Ward"]] = relationship("Ward")  # noqa: F821
    deliveries: Mapped[List["AlertDelivery"]] = relationship(
        "AlertDelivery", back_populates="alert", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[List["AlertAuditLog"]] = relationship(
        "AlertAuditLog", back_populates="alert", cascade="all, delete-orphan", order_by="AlertAuditLog.created_at"
    )


class CitizenSubscription(Base):
    """
    Anonymous, consent-based citizen subscription for localized flood warnings.
    Supports Web Push (VAPID), explicit location consent, and PostGIS 5 km proximity queries.
    Exact citizen locations are kept private and never exposed in operator triage or public telemetry.
    """
    __tablename__ = "citizen_subscriptions"
    __table_args__ = (
        UniqueConstraint("subscription_id", name="uq_citizen_subscriptions_id"),
        UniqueConstraint("endpoint", name="uq_citizen_subscriptions_endpoint"),
        CheckConstraint("preferred_language IN ('en', 'mr', 'hi')", name="chk_subscription_language"),
        CheckConstraint("min_severity IN ('watch', 'warning', 'critical')", name="chk_subscription_severity"),
        CheckConstraint("location_permission_status IN ('granted', 'prompt', 'denied')", name="chk_subscription_location_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth_key: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), default="web_push", server_default="web_push", nullable=False)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Explicit consent flags
    notification_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    location_consent: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    location_permission_status: Mapped[str] = mapped_column(String(20), default="prompt", server_default="prompt", nullable=False)
    consent_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # PostGIS location for 5 km proximity queries
    location: Mapped[Optional[Geometry]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326),
        nullable=True
    )
    location_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ward_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        ForeignKey("wards.ward_id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # User preferences
    preferred_language: Mapped[str] = mapped_column(String(10), default="en", server_default="en", nullable=False)
    min_severity: Mapped[str] = mapped_column(String(20), default="warning", server_default="warning", nullable=False)

    # Deactivation & unsubscribe lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False, index=True)
    deactivated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivation_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    ward: Mapped[Optional["Ward"]] = relationship("Ward")  # noqa: F821
    deliveries: Mapped[List["AlertDelivery"]] = relationship(
        "AlertDelivery", back_populates="subscription", cascade="all, delete-orphan"
    )


class AlertDelivery(Base):
    """
    Per-device notification delivery attempt and receipt status.
    Distinguishes queued, accepted, delivered, failed, expired, and cancelled states.
    Prevents duplicate deliveries via idempotency keys.
    """
    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_alert_deliveries_idempotency_key"),
        CheckConstraint(
            "status IN ('queued', 'accepted', 'delivered', 'failed', 'expired', 'cancelled')",
            name="chk_delivery_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("alerts_dispatched.alert_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    subscription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("citizen_subscriptions.subscription_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    channel: Mapped[str] = mapped_column(String(20), default="push", server_default="push", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", server_default="queued", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relationships
    alert: Mapped["AlertDispatched"] = relationship("AlertDispatched", back_populates="deliveries")
    subscription: Mapped["CitizenSubscription"] = relationship("CitizenSubscription", back_populates="deliveries")


class AlertAuditLog(Base):
    """
    Append-only audit trail of operator decisions and system lifecycle transitions.
    """
    __tablename__ = "alert_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("alerts_dispatched.alert_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    operator_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    alert: Mapped["AlertDispatched"] = relationship("AlertDispatched", back_populates="audit_logs")
