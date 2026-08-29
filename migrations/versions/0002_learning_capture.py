"""Add position_observations and exit_decisions

Phase 1 of the strategy improvement plan: make every managed position
reconstructable through its declared outcome without console logs.

Both tables are append-oriented. Nothing in the application updates a row once
written, and the downgrade drops them rather than attempting to preserve
partially-migrated data, because there is no earlier shape to preserve it into.

Revision ID: 0002_learning_capture
Revises: 0001_h0_baseline
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_learning_capture"
down_revision = "0001_h0_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_observations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("position_id", sa.String(64), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("snapshot_id", sa.String(128), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("long_bid", sa.Numeric(18, 6), nullable=True),
        sa.Column("short_ask", sa.Numeric(18, 6), nullable=True),
        sa.Column("spread_value", sa.Numeric(18, 6), nullable=True),
        sa.Column("underlying_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("underlying_source", sa.String(32), nullable=False),
        sa.Column("underlying_session", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dte", sa.Integer, nullable=False),
        sa.Column("sessions_elapsed", sa.Integer, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("data_quality", sa.JSON, nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_position_observations_position_id", "position_observations", ["position_id"]
    )
    op.create_index(
        "ix_position_observations_observed_at", "position_observations", ["observed_at"]
    )

    op.create_table(
        "exit_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("position_id", sa.String(64), sa.ForeignKey("positions.id"), nullable=False),
        sa.Column(
            "observation_id", sa.String(64),
            sa.ForeignKey("position_observations.id"), nullable=False,
        ),
        sa.Column("run_id", sa.String(64), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column("trigger", sa.String(32), nullable=False),
        sa.Column("should_close", sa.Boolean, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("evaluated", sa.JSON, nullable=False),
        sa.Column("precedence", sa.JSON, nullable=False),
        sa.Column("value_unmeasurable", sa.Boolean, nullable=False),
        sa.Column("invalidation_unverifiable", sa.Boolean, nullable=False),
        sa.Column("unrealized", sa.Numeric(18, 6), nullable=True),
        sa.Column("suggested_limit", sa.Numeric(18, 6), nullable=True),
        sa.Column("disposition", sa.String(48), nullable=False),
        sa.Column(
            "close_order_id", sa.String(64), sa.ForeignKey("broker_orders.id"), nullable=True
        ),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )
    op.create_index("ix_exit_decisions_position_id", "exit_decisions", ["position_id"])
    op.create_index("ix_exit_decisions_trigger", "exit_decisions", ["trigger"])
    op.create_index("ix_exit_decisions_decided_at", "exit_decisions", ["decided_at"])


def downgrade() -> None:
    # exit_decisions references position_observations, so it goes first.
    op.drop_index("ix_exit_decisions_decided_at", table_name="exit_decisions")
    op.drop_index("ix_exit_decisions_trigger", table_name="exit_decisions")
    op.drop_index("ix_exit_decisions_position_id", table_name="exit_decisions")
    op.drop_table("exit_decisions")

    op.drop_index("ix_position_observations_observed_at", table_name="position_observations")
    op.drop_index("ix_position_observations_position_id", table_name="position_observations")
    op.drop_table("position_observations")
