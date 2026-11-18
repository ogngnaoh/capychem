"""Preserve artifact directory identity in reproducible experiment exports."""

import sqlalchemy as sa
from alembic import op

revision = "c24d6e9a0f31"
down_revision = "b9822d08f610"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("experiment_artifacts", sa.Column("relative_path", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("experiment_artifacts", "relative_path")
