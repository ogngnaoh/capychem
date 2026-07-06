"""add run manifest_json + oracle_call oracle_version (m07-06)

Revision ID: 38f369ef45a6
Revises: 0cc25e46d571
Create Date: 2026-07-06 14:50:29.666944

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "38f369ef45a6"
down_revision: str | Sequence[str] | None = "0cc25e46d571"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # OD-5 provenance; both nullable, no backfill (pre-07-06 runs have no manifest).
    op.add_column(
        "oracle_calls", sa.Column("oracle_version", sa.String(length=32), nullable=True)
    )
    op.add_column("runs", sa.Column("manifest_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "manifest_json")
    op.drop_column("oracle_calls", "oracle_version")
