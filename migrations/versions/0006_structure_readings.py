"""Persist what the structure gate computed, signal or not

`CIIP-VAL-012`. `evidence.build_signals` returns `[]` the moment a gate declines,
so a refusal reached the records carrying nothing: 201 live decisions had zero
signal rows, and nothing recorded said whether the trend missed by a hair or was
absent. Over that many refusals it is the difference between a strategy waiting
for a rare setup and one effectively switched off.

One row per decision, written in the decision's own transaction. Not back-filled:
the bars those decisions were made on were never stored, so the readings cannot be
reconstructed, and inventing them would be worse than their absence.

Revision ID: 0006_structure_readings
Revises: 0005_decision_outcomes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_structure_readings"
down_revision = "0005_decision_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "structure_readings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("decision_id", sa.String(64), sa.ForeignKey("decisions.id"),
                  nullable=False, unique=True),
        sa.Column("market_snapshot_id", sa.String(64), sa.ForeignKey("market_snapshots.id"),
                  nullable=False, index=True),
        sa.Column("gate", sa.String(32), nullable=False, index=True),
        sa.Column("bars_considered", sa.Integer(), nullable=False),
        sa.Column("bars_required", sa.Integer(), nullable=False),
        sa.Column("fast_ema", sa.Numeric(18, 6), nullable=True),
        sa.Column("slow_ema", sa.Numeric(18, 6), nullable=True),
        sa.Column("separation", sa.Numeric(18, 8), nullable=True),
        sa.Column("last_close", sa.Numeric(18, 6), nullable=True),
        sa.Column("close_side", sa.String(8), nullable=True),
        sa.Column("retest_touched", sa.Boolean(), nullable=True),
        sa.Column("separation_shortfall", sa.Numeric(18, 8), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("structure_readings")
