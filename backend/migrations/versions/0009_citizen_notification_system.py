"""Add citizen notification system: subscriptions, alert lifecycle, deliveries, and audit log.

Revision ID: 0009_citizen_notification_system
Revises: 0008_citizen_report_nlp
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

revision: str = "0009_citizen_notification_system"
down_revision: Union[str, None] = "0008_citizen_report_nlp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update alerts_dispatched with lifecycle, coordinates, radius, and approval columns
    op.add_column(
        "alerts_dispatched",
        sa.Column("status", sa.String(length=32), server_default="completed", nullable=False),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column(
            "center_location",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("radius_km", sa.Float(), server_default="5.0", nullable=False),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("instruction", sa.Text(), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("created_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("approved_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("cancelled_by", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("delivery_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "alerts_dispatched",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index(
        "ix_alerts_dispatched_idempotency_key",
        "alerts_dispatched",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_alerts_dispatched_status",
        "alerts_dispatched",
        ["status"],
    )
    op.create_check_constraint(
        "chk_alerts_status",
        "alerts_dispatched",
        "status IN ('draft', 'pending_approval', 'approved', 'queued', 'dispatching', 'completed', 'partially_failed', 'failed', 'cancelled', 'expired')",
    )

    # 2. Create citizen_subscriptions table
    op.create_table(
        "citizen_subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth_key", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), server_default="web_push", nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("notification_consent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("location_consent", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("location_permission_status", sa.String(length=20), server_default="prompt", nullable=False),
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", Geometry(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ward_id", sa.String(length=20), nullable=True),
        sa.Column("preferred_language", sa.String(length=10), server_default="en", nullable=False),
        sa.Column("min_severity", sa.String(length=20), server_default="warning", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivation_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["ward_id"], ["wards.ward_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", name="uq_citizen_subscriptions_id"),
        sa.UniqueConstraint("endpoint", name="uq_citizen_subscriptions_endpoint"),
        sa.CheckConstraint(
            "preferred_language IN ('en', 'mr', 'hi')",
            name="chk_subscription_language",
        ),
        sa.CheckConstraint(
            "min_severity IN ('watch', 'warning', 'critical')",
            name="chk_subscription_severity",
        ),
        sa.CheckConstraint(
            "location_permission_status IN ('granted', 'prompt', 'denied')",
            name="chk_subscription_location_status",
        ),
    )

    op.create_index(
        "ix_citizen_subscriptions_subscription_id",
        "citizen_subscriptions",
        ["subscription_id"],
    )
    op.create_index(
        "ix_citizen_subscriptions_location_updated_at",
        "citizen_subscriptions",
        ["location_updated_at"],
    )
    op.create_index(
        "ix_citizen_subscriptions_is_active",
        "citizen_subscriptions",
        ["is_active"],
    )
    op.create_index(
        "ix_citizen_subscriptions_ward_id",
        "citizen_subscriptions",
        ["ward_id"],
    )

    # 3. Create alert_deliveries table
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=50), nullable=False),
        sa.Column("subscription_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=20), server_default="push", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts_dispatched.alert_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["citizen_subscriptions.subscription_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_alert_deliveries_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('queued', 'accepted', 'delivered', 'failed', 'expired', 'cancelled')",
            name="chk_delivery_status",
        ),
    )

    op.create_index("ix_alert_deliveries_alert_id", "alert_deliveries", ["alert_id"])
    op.create_index("ix_alert_deliveries_subscription_id", "alert_deliveries", ["subscription_id"])
    op.create_index("ix_alert_deliveries_status", "alert_deliveries", ["status"])

    # 4. Create alert_audit_logs table
    op.create_table(
        "alert_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.String(length=50), nullable=False),
        sa.Column("operator_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts_dispatched.alert_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_alert_audit_logs_alert_id", "alert_audit_logs", ["alert_id"])
    op.create_index("ix_alert_audit_logs_operator_id", "alert_audit_logs", ["operator_id"])


def downgrade() -> None:
    op.drop_table("alert_audit_logs")
    op.drop_table("alert_deliveries")
    op.drop_table("citizen_subscriptions")
    op.drop_constraint("chk_alerts_status", "alerts_dispatched", type_="check")
    op.drop_index("ix_alerts_dispatched_status", table_name="alerts_dispatched")
    op.drop_index("idx_alerts_dispatched_center_location", table_name="alerts_dispatched")
    op.drop_index("ix_alerts_dispatched_idempotency_key", table_name="alerts_dispatched")
    op.drop_column("alerts_dispatched", "updated_at")
    op.drop_column("alerts_dispatched", "created_at")
    op.drop_column("alerts_dispatched", "delivery_summary")
    op.drop_column("alerts_dispatched", "idempotency_key")
    op.drop_column("alerts_dispatched", "cancellation_reason")
    op.drop_column("alerts_dispatched", "cancelled_by")
    op.drop_column("alerts_dispatched", "cancelled_at")
    op.drop_column("alerts_dispatched", "expires_at")
    op.drop_column("alerts_dispatched", "approved_at")
    op.drop_column("alerts_dispatched", "approved_by")
    op.drop_column("alerts_dispatched", "created_by")
    op.drop_column("alerts_dispatched", "instruction")
    op.drop_column("alerts_dispatched", "radius_km")
    op.drop_column("alerts_dispatched", "center_location")
    op.drop_column("alerts_dispatched", "status")
