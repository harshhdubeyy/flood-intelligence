"""Add citizen report NLP derived analysis table.

Revision ID: 0008_citizen_report_nlp
Revises: 0007_social_data_lifecycle
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_citizen_report_nlp"
down_revision: Union[str, None] = "0007_social_data_lifecycle"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "citizen_report_nlp_analysis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.String(length=36), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("urgency_score", sa.Float(), nullable=False),
        sa.Column("is_flood_related", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_waterlogging", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_spam", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("detected_language", sa.String(length=12), server_default="en", nullable=False),
        sa.Column("extracted_depth_m", sa.Float(), nullable=True),
        sa.Column("extracted_landmarks", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("matched_keywords", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "classification IN ('waterlogging', 'urgent', 'evacuation_needed', 'noise', 'spam', 'general_weather')",
            name="chk_report_nlp_classification",
        ),
        sa.CheckConstraint(
            "detected_language IN ('en', 'mr', 'hi', 'und')",
            name="chk_report_nlp_language",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_report_nlp_confidence",
        ),
        sa.CheckConstraint(
            "urgency_score >= 0.0 AND urgency_score <= 1.0",
            name="chk_report_nlp_urgency",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["citizen_reports.report_id"],
            name="fk_citizen_report_nlp_report_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", name="uq_citizen_report_nlp_report_id"),
    )
    op.create_index(
        "ix_citizen_report_nlp_report_id",
        "citizen_report_nlp_analysis",
        ["report_id"],
    )
    op.create_index(
        "ix_citizen_report_nlp_classification",
        "citizen_report_nlp_analysis",
        ["classification"],
    )


def downgrade() -> None:
    op.drop_index("ix_citizen_report_nlp_classification", table_name="citizen_report_nlp_analysis")
    op.drop_index("ix_citizen_report_nlp_report_id", table_name="citizen_report_nlp_analysis")
    op.drop_table("citizen_report_nlp_analysis")
