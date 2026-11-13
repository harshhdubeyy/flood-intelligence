"""Align citizen_reports columns with SQLAlchemy model.

Revision ID: 0002_report_schema_alignment
Revises: 0001_initial_schema
Create Date: 2026-09-10 00:00:00.000000

This migration documents the alignment between the ``citizen_reports`` table
columns and the SQLAlchemy ORM model (``backend/models/report.py``).

The model defines these columns:
    water_depth, image_url, cv_verified, cv_water_depth_m, cv_confidence,
    description, is_duplicate, duplicate_of_id, submitted_at

The initial migration (0001) used older/different column names
(photo_url, photo_verified, depth_est_m, status). This migration records
the intended schema and makes no destructive changes:

- No tables are dropped.
- No data is deleted.
- No existing columns are removed.

The live database already matches the current SQLAlchemy model, so this
revision is a documentation/no-op alignment. ``create_all()`` does NOT
alter existing tables, so any pre-existing schema drift must be
reconciled manually or via a future targeted ALTER migration.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002_report_schema_alignment'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    """Record schema alignment (no-op; no destructive changes)."""
    # No ALTER operations: the live schema already matches the model.
    # This migration exists to document the intended column names and
    # prevent accidental table recreation/drops.
    pass


def downgrade() -> None:
    """No-op downgrade; no data is removed."""
    pass