"""Add verified worker health and optimistic review decision revisions."""

import sqlalchemy as sa
from alembic import op

revision = "b9822d08f610"
down_revision = "602e7d648535"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiment_attempts", sa.Column("result_summary", sa.JSON(), nullable=True))
    op.add_column("experiment_worker_heartbeats", sa.Column("health", sa.JSON(), nullable=True))
    op.add_column(
        "experiment_decisions",
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("experiment_decisions", "revision")
    op.drop_column("experiment_worker_heartbeats", "health")
    op.drop_column("experiment_attempts", "result_summary")
