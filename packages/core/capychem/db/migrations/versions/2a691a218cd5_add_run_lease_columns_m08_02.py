"""add run lease columns m08 02

Revision ID: 2a691a218cd5
Revises: 38f369ef45a6
Create Date: 2026-07-07 18:09:30.987902

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a691a218cd5"
down_revision: str | Sequence[str] | None = "38f369ef45a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Durable job queue (m08-02): the lease a claimer holds while driving a run,
    # plus a heartbeat. All nullable -- a fresh/terminal row carries no lease.
    op.add_column("runs", sa.Column("lease_owner", sa.String(length=128), nullable=True))
    op.add_column("runs", sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    op.add_column("runs", sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    op.create_index("ix_run_status_lease", "runs", ["status", "lease_expires_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_run_status_lease", table_name="runs")
    op.drop_column("runs", "heartbeat_at")
    op.drop_column("runs", "lease_expires_at")
    op.drop_column("runs", "lease_owner")
