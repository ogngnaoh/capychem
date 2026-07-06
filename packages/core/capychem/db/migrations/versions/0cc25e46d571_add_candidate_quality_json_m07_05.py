"""add candidate quality_json (m07-05)

Revision ID: 0cc25e46d571
Revises: ed2d80a8ccda
Create Date: 2026-07-06 14:35:07.852244

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0cc25e46d571"
down_revision: str | Sequence[str] | None = "ed2d80a8ccda"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Per-candidate quality report (07-05); nullable, no backfill (pre-07-05 candidates
    # simply have no report).
    op.add_column("candidates", sa.Column("quality_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("candidates", "quality_json")
