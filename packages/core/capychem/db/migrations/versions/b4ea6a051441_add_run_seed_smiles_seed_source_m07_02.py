"""add run seed_smiles + seed_source (m07-02)

Revision ID: b4ea6a051441
Revises: f8342ecfc066
Create Date: 2026-07-06 12:05:58.594559

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4ea6a051441"
down_revision: str | Sequence[str] | None = "f8342ecfc066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Operator bring-your-own compounds (07-02, FR-001); nullable, no backfill.
    op.add_column("runs", sa.Column("seed_smiles", sa.JSON(), nullable=True))
    # seed_source is NOT NULL; server_default="default" backfills existing rows
    # (every pre-07-02 run used the default pool), then is dropped so future inserts
    # rely on the ORM-side default only — mirrors the mode/max_generations backfill
    # pattern so compare_metadata sees no server_default drift against Base.metadata.
    op.add_column(
        "runs",
        sa.Column("seed_source", sa.String(length=16), nullable=False, server_default="default"),
    )
    op.alter_column("runs", "seed_source", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "seed_source")
    op.drop_column("runs", "seed_smiles")
