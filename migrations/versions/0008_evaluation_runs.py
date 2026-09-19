"""Evaluation runs

`CIIP-3`'s last append-oriented entity, built now that something can fill it.
It was deliberately left out of `CIIP-009` on the grounds that "recording a run
before anything can produce one would be scaffolding pretending to be evidence".
Two harnesses now produce runs — `sensitivity` and `gate_study` — and their
numbers currently live only in prose, which is the failure this project guards
against everywhere else.

Deliberately narrower than the specification. `CIIP-3` asks for folds, costs,
stress and regime slices too; none of those has been designed, so a run names
them in `not_covered` rather than carrying an empty column that would read as a
run which considered them and found nothing.

Empty on arrival. Nothing reads this table: it is a record, not an input, and no
decision path consults it.

Revision ID: 0008_evaluation_runs
Revises: 0007_strategy_catalog
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_evaluation_runs"
down_revision = "0007_strategy_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("harness", sa.String(length=64), nullable=False),
        sa.Column("code_revision", sa.String(length=64), nullable=False),
        sa.Column("dataset_manifest", sa.JSON(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("not_covered", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_evaluation_runs_harness", "evaluation_runs", ["harness"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_harness", table_name="evaluation_runs")
    op.drop_table("evaluation_runs")
