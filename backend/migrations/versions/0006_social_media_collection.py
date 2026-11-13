"""Add source-preserving social media collection tables.

Revision ID: 0006_social_media_collection
Revises: 0005_location_validation_status
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_social_media_collection"
down_revision: Union[str, None] = "0005_location_validation_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_media_posts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("external_post_id", sa.String(length=256), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("location_text", sa.String(length=512), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("ward_id", sa.String(length=20), nullable=True),
        sa.Column("geolocation_confidence", sa.Float(), nullable=True),
        sa.Column("ward_assignment_provenance", sa.String(length=64), nullable=True),
        sa.Column(
            "matched_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "media_references",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "processing_status",
            sa.String(length=32),
            server_default="collected",
            nullable=False,
        ),
        sa.Column(
            "source_provenance",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL AND "
            "latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="chk_social_media_post_coordinate_pair",
        ),
        sa.CheckConstraint(
            "geolocation_confidence IS NULL OR geolocation_confidence BETWEEN 0 AND 1",
            name="chk_social_media_post_geolocation_confidence",
        ),
        sa.ForeignKeyConstraint(["ward_id"], ["wards.ward_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "external_post_id",
            name="uq_social_media_posts_platform_external",
        ),
    )
    op.create_index("ix_social_media_posts_platform", "social_media_posts", ["platform"])
    op.create_index("ix_social_media_posts_posted_at", "social_media_posts", ["posted_at"])
    op.create_index(
        "ix_social_media_posts_collected_at", "social_media_posts", ["collected_at"]
    )
    op.create_index("ix_social_media_posts_ward_id", "social_media_posts", ["ward_id"])
    op.create_index(
        "ix_social_media_posts_processing_status",
        "social_media_posts",
        ["processing_status"],
    )
    op.create_table(
        "social_collection_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("collected_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=48), nullable=True),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('success', 'error', 'not_configured', 'disabled')",
            name="chk_social_collection_run_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_social_collection_runs_platform_completed",
        "social_collection_runs",
        ["platform", "completed_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM social_media_posts")).scalar_one():
        raise RuntimeError("Refusing to remove collected social media records.")
    if bind.execute(sa.text("SELECT COUNT(*) FROM social_collection_runs")).scalar_one():
        raise RuntimeError("Refusing to remove social collection run history.")
    op.drop_index(
        "ix_social_collection_runs_platform_completed", table_name="social_collection_runs"
    )
    op.drop_table("social_collection_runs")
    op.drop_index(
        "ix_social_media_posts_processing_status", table_name="social_media_posts"
    )
    op.drop_index("ix_social_media_posts_ward_id", table_name="social_media_posts")
    op.drop_index("ix_social_media_posts_collected_at", table_name="social_media_posts")
    op.drop_index("ix_social_media_posts_posted_at", table_name="social_media_posts")
    op.drop_index("ix_social_media_posts_platform", table_name="social_media_posts")
    op.drop_table("social_media_posts")
