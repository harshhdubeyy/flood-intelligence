"""Record whether operator-reviewed locations match a unique Mumbai ward.

Revision ID: 0005_location_validation_status
Revises: 0004_flood_ground_truth
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_location_validation_status"
down_revision: Union[str, None] = "0004_flood_ground_truth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "flood_events",
        sa.Column("location_validation_status", sa.String(length=24), nullable=True),
    )
    op.create_check_constraint(
        "chk_flood_event_location_validation_status",
        "flood_events",
        "location_validation_status IS NULL OR "
        "location_validation_status IN ('matched', 'outside_wards', 'ambiguous_boundary')",
    )
    op.add_column(
        "flood_event_verification_history",
        sa.Column("location_validation_status", sa.String(length=24), nullable=True),
    )
    op.create_check_constraint(
        "chk_flood_history_location_validation_status",
        "flood_event_verification_history",
        "location_validation_status IS NULL OR "
        "location_validation_status IN ('matched', 'outside_wards', 'ambiguous_boundary')",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT COUNT(*) FROM flood_event_verification_history")
    ).scalar_one():
        raise RuntimeError("Refusing to remove location validation from audit history.")
    if bind.execute(sa.text("SELECT COUNT(*) FROM flood_events")).scalar_one():
        raise RuntimeError("Refusing to remove location validation from flood events.")

    op.drop_constraint(
        "chk_flood_history_location_validation_status",
        "flood_event_verification_history",
        type_="check",
    )
    op.drop_column("flood_event_verification_history", "location_validation_status")
    op.drop_constraint(
        "chk_flood_event_location_validation_status",
        "flood_events",
        type_="check",
    )
    op.drop_column("flood_events", "location_validation_status")
