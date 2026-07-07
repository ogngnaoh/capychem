"""unique generation run index m08 02b

Revision ID: c89f6ae510ec
Revises: 2a691a218cd5
Create Date: 2026-07-07 19:21:26.083229

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c89f6ae510ec"
down_revision: str | Sequence[str] | None = "2a691a218cd5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Structural backstop against a revived-zombie writer (m08-02b): a worker
    # whose lease expired and was reclaimed, but whose stalled event loop
    # resumed and tried to persist a generation index a new owner already
    # wrote. Dedup FIRST -- the shared dev DB already has pre-existing
    # duplicate (run_id, index) rows from an earlier orphaned-worker episode
    # (m08-02 evaluation), so creating the UNIQUE constraint would otherwise
    # fail here. Keep the lowest id per (run_id, index); ON DELETE CASCADE on
    # candidates.generation_id / oracle_calls.candidate_id (see 0001_baseline)
    # cleans up the deleted generations' children automatically.
    op.execute(
        """
        DELETE FROM generations
        WHERE id NOT IN (
            SELECT MIN(id) FROM generations GROUP BY run_id, index
        )
        """
    )
    op.drop_index("ix_generation_run_index", table_name="generations")
    op.create_unique_constraint("uq_generation_run_index", "generations", ["run_id", "index"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_generation_run_index", "generations", type_="unique")
    op.create_index("ix_generation_run_index", "generations", ["run_id", "index"], unique=False)
