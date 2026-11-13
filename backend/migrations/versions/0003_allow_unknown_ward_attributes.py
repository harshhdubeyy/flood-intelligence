"""Allow unprovided static ward attributes to remain unknown.

Revision ID: 0003_nullable_ward_attrs
Revises: 0002_report_schema_alignment
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_nullable_ward_attrs"
down_revision: Union[str, None] = "0002_report_schema_alignment"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "wards",
        "is_coastal",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "wards",
        "drainage_index",
        existing_type=sa.Float(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM wards
                WHERE is_coastal IS NULL OR drainage_index IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade while ward coastal/drainage attributes are unknown.';
            END IF;
        END
        $$;
        """
    )
    op.alter_column(
        "wards",
        "is_coastal",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
    op.alter_column(
        "wards",
        "drainage_index",
        existing_type=sa.Float(),
        nullable=False,
        server_default=sa.text("0.5"),
    )
