"""add oracle score cache m08 04

Revision ID: 8d09b43b3c0b
Revises: c89f6ae510ec
Create Date: 2026-07-07 20:32:54.649892

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d09b43b3c0b"
down_revision: str | Sequence[str] | None = "c89f6ae510ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Persistent, cross-run oracle-score cache (m08-04). UniqueConstraint on the
    # lookup key is index-backed (Postgres builds a btree for it), satisfying both
    # the uniqueness and the index requirement in one object.
    op.create_table(
        "oracle_score_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("oracle_key", sa.String(length=64), nullable=False),
        sa.Column("objective_key", sa.String(length=128), nullable=False),
        sa.Column("canonical_smiles", sa.String(length=512), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("wall_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "oracle_key", "objective_key", "canonical_smiles", name="uq_oracle_score_cache_key"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("oracle_score_cache")
