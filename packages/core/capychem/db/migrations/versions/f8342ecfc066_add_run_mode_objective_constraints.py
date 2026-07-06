"""add run mode + objective/constraints columns (m07 slice 01)

Revision ID: f8342ecfc066
Revises: f4251d568ae6
Create Date: 2026-07-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8342ecfc066"
down_revision: str | Sequence[str] | None = "f4251d568ae6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # mode is NOT NULL; server_default="benchmark" backfills existing rows (every
    # pre-07 run was a benchmark run), then is dropped so future inserts rely on the
    # ORM-side default only — mirrors the max_generations backfill pattern so
    # compare_metadata sees no server_default drift against Base.metadata.
    op.add_column(
        "runs", sa.Column("mode", sa.String(length=16), nullable=False, server_default="benchmark")
    )
    op.alter_column("runs", "mode", server_default=None)
    # Nullable JSON specs, populated by later 07 slices; no backfill needed.
    op.add_column("runs", sa.Column("objective_json", sa.JSON(), nullable=True))
    op.add_column("runs", sa.Column("constraints_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "constraints_json")
    op.drop_column("runs", "objective_json")
    op.drop_column("runs", "mode")
