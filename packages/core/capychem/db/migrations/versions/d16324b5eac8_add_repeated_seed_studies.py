"""Persist immutable repeated-seed studies over existing experiment jobs."""

import sqlalchemy as sa
from alembic import op

revision = "d16324b5eac8"
down_revision = "c24d6e9a0f31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiment_studies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("base_spec", sa.JSON(), nullable=False),
        sa.Column("seed_pairs", sa.JSON(), nullable=False),
        sa.Column("spec_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "experiment_study_members",
        sa.Column(
            "experiment_id", sa.String(36), sa.ForeignKey("experiments.id"), primary_key=True
        ),
        sa.Column(
            "study_id", sa.String(36), sa.ForeignKey("experiment_studies.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.UniqueConstraint("study_id", "ordinal", name="uq_study_member_ordinal"),
    )
    op.create_index(
        "ix_experiment_study_members_study_id", "experiment_study_members", ["study_id"]
    )


def downgrade() -> None:
    op.drop_table("experiment_study_members")
    op.drop_table("experiment_studies")
