"""Add operator-reviewed flood events and immutable verification history.

Revision ID: 0004_flood_ground_truth
Revises: 0003_nullable_ward_attrs
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0004_flood_ground_truth"
down_revision: Union[str, None] = "0003_nullable_ward_attrs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "citizen_reports",
        sa.Column(
            "operator_verification_status",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "chk_citizen_report_operator_verification_status",
        "citizen_reports",
        "operator_verification_status IN ('pending', 'confirmed', 'rejected', 'review_required')",
    )
    op.create_index(
        "ix_citizen_reports_operator_verification_status",
        "citizen_reports",
        ["operator_verification_status"],
    )

    op.create_table(
        "flood_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_record_id", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("ward_id", sa.String(length=20), nullable=True),
        sa.Column("water_depth", sa.String(length=20), nullable=True),
        sa.Column("water_depth_m", sa.Float(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("duplicate_of_report_id", sa.String(length=36), nullable=True),
        sa.Column("location_description", sa.String(length=500), nullable=True),
        sa.Column(
            "evidence_image_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("verification_status", sa.String(length=24), nullable=False),
        sa.Column("verified_by", sa.String(length=100), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "official_confirmation",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("verification_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_kind IN ('citizen_report', 'field_observation', 'bmc_record')",
            name="chk_flood_event_source_kind",
        ),
        sa.CheckConstraint(
            "verification_status IN ('operator_confirmed', 'rejected', 'review_required')",
            name="chk_flood_event_verification_status",
        ),
        sa.CheckConstraint(
            "water_depth IS NULL OR water_depth IN ('ankle', 'knee', 'waist', 'submerged')",
            name="chk_flood_event_water_depth",
        ),
        sa.CheckConstraint(
            "water_depth_m IS NULL OR water_depth_m >= 0",
            name="chk_flood_event_water_depth_m",
        ),
        sa.ForeignKeyConstraint(
            ["ward_id"], ["wards.ward_id"], name="fk_flood_events_ward_id_wards", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_flood_events"),
        sa.UniqueConstraint("event_id", name="uq_flood_events_event_id"),
        sa.UniqueConstraint(
            "source_kind", "source_record_id", name="uq_flood_event_source_record"
        ),
    )
    op.create_index("ix_flood_events_source_kind", "flood_events", ["source_kind"])
    op.create_index("ix_flood_events_event_timestamp", "flood_events", ["event_timestamp"])
    op.create_index("ix_flood_events_ward_id", "flood_events", ["ward_id"])
    op.create_index("ix_flood_events_verification_status", "flood_events", ["verification_status"])
    op.create_index(
        "idx_flood_events_location",
        "flood_events",
        ["location"],
        postgresql_using="gist",
    )

    op.create_table(
        "flood_event_verification_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=True),
        sa.Column("operator_id", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("previous_status", sa.String(length=24), nullable=False),
        sa.Column("new_status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("ward_id", sa.String(length=20), nullable=True),
        sa.Column("water_depth", sa.String(length=20), nullable=True),
        sa.Column("water_depth_m", sa.Float(), nullable=True),
        sa.Column("is_duplicate", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("duplicate_of_report_id", sa.String(length=36), nullable=True),
        sa.Column(
            "evidence_image_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('confirm', 'reject', 'review', 'evidence_added')",
            name="chk_flood_event_history_action",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["citizen_reports.report_id"],
            name="fk_flood_event_history_report_id_citizen_reports",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["flood_events.event_id"],
            name="fk_flood_event_history_event_id_flood_events",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ward_id"], ["wards.ward_id"], name="fk_flood_event_history_ward_id_wards", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_flood_event_verification_history"),
    )
    op.create_index(
        "ix_flood_event_verification_history_report_id",
        "flood_event_verification_history",
        ["report_id"],
    )
    op.create_index(
        "ix_flood_event_verification_history_event_id",
        "flood_event_verification_history",
        ["event_id"],
    )
    op.create_index(
        "ix_flood_event_verification_history_occurred_at",
        "flood_event_verification_history",
        ["occurred_at"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_flood_event_history_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'flood event verification history is append-only';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER flood_event_verification_history_append_only
        BEFORE UPDATE OR DELETE ON flood_event_verification_history
        FOR EACH ROW EXECUTE FUNCTION prevent_flood_event_history_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    history_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM flood_event_verification_history")
    ).scalar_one()
    event_count = bind.execute(sa.text("SELECT COUNT(*) FROM flood_events")).scalar_one()
    if history_count or event_count:
        raise RuntimeError(
            "Refusing to drop flood-event records or verification history during downgrade."
        )

    op.drop_index(
        "ix_flood_event_verification_history_occurred_at",
        table_name="flood_event_verification_history",
    )
    op.execute(
        "DROP TRIGGER flood_event_verification_history_append_only "
        "ON flood_event_verification_history"
    )
    op.drop_index(
        "ix_flood_event_verification_history_event_id",
        table_name="flood_event_verification_history",
    )
    op.drop_index(
        "ix_flood_event_verification_history_report_id",
        table_name="flood_event_verification_history",
    )
    op.drop_table("flood_event_verification_history")
    op.execute("DROP FUNCTION prevent_flood_event_history_mutation()")
    op.drop_index("idx_flood_events_location", table_name="flood_events")
    op.drop_index("ix_flood_events_verification_status", table_name="flood_events")
    op.drop_index("ix_flood_events_ward_id", table_name="flood_events")
    op.drop_index("ix_flood_events_event_timestamp", table_name="flood_events")
    op.drop_index("ix_flood_events_source_kind", table_name="flood_events")
    op.drop_table("flood_events")
    op.drop_index(
        "ix_citizen_reports_operator_verification_status", table_name="citizen_reports"
    )
    op.drop_constraint(
        "chk_citizen_report_operator_verification_status",
        "citizen_reports",
        type_="check",
    )
    op.drop_column("citizen_reports", "operator_verification_status")
