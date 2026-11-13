"""Add fail-closed social retention, reconciliation, and compliance records.

Revision ID: 0007_social_data_lifecycle
Revises: 0006_social_media_collection
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_social_data_lifecycle"
down_revision: Union[str, None] = "0006_social_media_collection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "social_media_posts",
        "external_post_id",
        existing_type=sa.String(length=256),
        nullable=True,
    )
    op.add_column(
        "social_media_posts",
        sa.Column(
            "source_status",
            sa.String(length=32),
            server_default="unverified",
            nullable=False,
        ),
    )
    op.add_column(
        "social_media_posts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "social_media_posts",
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "social_media_posts",
        sa.Column("next_reconcile_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "social_media_posts",
        sa.Column(
            "reconcile_attempt_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "chk_social_media_post_source_status",
        "social_media_posts",
        "source_status IN ('unverified', 'current', 'pending_compliance', "
        "'unavailable', 'expired', 'deleted')",
    )
    op.create_index(
        "ix_social_media_posts_source_status_next_reconcile",
        "social_media_posts",
        ["source_status", "next_reconcile_at"],
    )
    op.create_index(
        "ix_social_media_posts_expires_at",
        "social_media_posts",
        ["expires_at"],
    )

    op.drop_constraint(
        "chk_social_collection_run_status", "social_collection_runs", type_="check"
    )
    op.create_check_constraint(
        "chk_social_collection_run_status",
        "social_collection_runs",
        "status IN ('success', 'error', 'not_configured', 'disabled', 'policy_blocked')",
    )

    op.create_table(
        "social_post_derived_artifacts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("social_post_id", sa.Integer(), nullable=False),
        sa.Column("artifact_type", sa.String(length=24), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "artifact_type IN ('nlp', 'cv', 'location', 'summary', 'search_index')",
            name="chk_social_post_derived_artifact_type",
        ),
        sa.ForeignKeyConstraint(
            ["social_post_id"],
            ["social_media_posts.id"],
            name="fk_social_post_derived_artifacts_post_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_social_post_derived_artifacts_post_id",
        "social_post_derived_artifacts",
        ["social_post_id"],
    )

    op.create_table(
        "social_compliance_tombstones",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("source_id_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "source_id_digest",
            name="uq_social_tombstone_platform_digest",
        ),
    )

    op.create_table(
        "social_compliance_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("operation_type", sa.String(length=32), nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=True),
        sa.Column("trigger_source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column("outcome", sa.String(length=48), nullable=False),
        sa.Column("event_id_digest", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'retryable', 'failed', 'dry_run')",
            name="chk_social_compliance_operation_status",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["social_media_posts.id"],
            name="fk_social_compliance_operations_post_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_id",
            "attempt_number",
            name="uq_social_compliance_operation_attempt",
        ),
    )
    op.create_index(
        "ix_social_compliance_operations_status_created",
        "social_compliance_operations",
        ["status", "created_at"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_social_compliance_operation_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'social compliance operation records are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_social_compliance_operations_append_only
        BEFORE UPDATE OR DELETE ON social_compliance_operations
        FOR EACH ROW EXECUTE FUNCTION reject_social_compliance_operation_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_social_compliance_operations_no_truncate
        BEFORE TRUNCATE ON social_compliance_operations
        FOR EACH STATEMENT EXECUTE FUNCTION reject_social_compliance_operation_mutation()
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in (
        "social_compliance_operations",
        "social_compliance_tombstones",
        "social_post_derived_artifacts",
    ):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError(f"Refusing to remove populated {table} lifecycle data.")
    if bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM social_media_posts "
            "WHERE external_post_id IS NULL"
        )
    ).scalar_one():
        raise RuntimeError("Refusing to restore NOT NULL while redacted records exist.")

    op.execute(
        "DROP TRIGGER trg_social_compliance_operations_no_truncate "
        "ON social_compliance_operations"
    )
    op.execute(
        "DROP TRIGGER trg_social_compliance_operations_append_only ON social_compliance_operations"
    )
    op.execute("DROP FUNCTION reject_social_compliance_operation_mutation()")
    op.drop_index(
        "ix_social_compliance_operations_status_created",
        table_name="social_compliance_operations",
    )
    op.drop_table("social_compliance_operations")
    op.drop_table("social_compliance_tombstones")
    op.drop_index(
        "ix_social_post_derived_artifacts_post_id",
        table_name="social_post_derived_artifacts",
    )
    op.drop_table("social_post_derived_artifacts")
    op.drop_constraint(
        "chk_social_collection_run_status", "social_collection_runs", type_="check"
    )
    op.create_check_constraint(
        "chk_social_collection_run_status",
        "social_collection_runs",
        "status IN ('success', 'error', 'not_configured', 'disabled')",
    )
    op.drop_index(
        "ix_social_media_posts_source_status_next_reconcile",
        table_name="social_media_posts",
    )
    op.drop_index("ix_social_media_posts_expires_at", table_name="social_media_posts")
    op.drop_constraint(
        "chk_social_media_post_source_status", "social_media_posts", type_="check"
    )
    op.drop_column("social_media_posts", "reconcile_attempt_count")
    op.drop_column("social_media_posts", "next_reconcile_at")
    op.drop_column("social_media_posts", "last_verified_at")
    op.drop_column("social_media_posts", "expires_at")
    op.drop_column("social_media_posts", "source_status")
    op.alter_column(
        "social_media_posts",
        "external_post_id",
        existing_type=sa.String(length=256),
        nullable=False,
    )
