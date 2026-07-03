"""add max_generations to runs

Revision ID: f4251d568ae6
Revises: 0001
Create Date: 2026-07-03 04:20:38.368925

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4251d568ae6"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # server_default backfills existing rows (matches CreateRunRequest's default of
    # 100), then is dropped so future inserts rely on the ORM-side default only.
    op.add_column(
        "runs", sa.Column("max_generations", sa.Integer(), nullable=False, server_default="100")
    )
    op.alter_column("runs", "max_generations", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "max_generations")
