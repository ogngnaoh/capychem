"""widen runs.status to 32 for constraint_starved (m07-04b)

Revision ID: ed2d80a8ccda
Revises: b4ea6a051441
Create Date: 2026-07-06 14:28:17.642638

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ed2d80a8ccda"
down_revision: str | Sequence[str] | None = "b4ea6a051441"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # The 07-04b terminal status "constraint_starved" (18 chars) overflows VARCHAR(16).
    # Widen to 32 (headroom for future status names). Pure widening — no data change.
    op.alter_column(
        "runs",
        "status",
        existing_type=sa.VARCHAR(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "runs",
        "status",
        existing_type=sa.String(length=32),
        type_=sa.VARCHAR(length=16),
        existing_nullable=False,
    )
