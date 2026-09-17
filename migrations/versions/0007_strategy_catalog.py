"""Strategy candidates, policy versions, and promotion decisions

`CIIP-009`. The competitors' strategy-lifecycle vocabulary as records rather than
language. A candidate carries its hypothesis, permitted instruments and parameter
hash; a policy version carries the thresholds in force and what preceded them;
a promotion decision carries why a candidate moved, cited both ways.

Empty on arrival, and honestly so: no candidate has been proposed yet. The tables
exist so that the first one is recorded rather than described.

Nothing here grants authority. A candidate in `PAPER_ACTIVE` still reaches the
broker only through an approved intent and the gateway's own guards, which do not
consult these tables.

Revision ID: 0007_strategy_catalog
Revises: 0006_structure_readings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_strategy_catalog"
down_revision = "0006_structure_readings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(64), nullable=False, unique=True),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("thresholds", sa.JSON(), nullable=False),
        sa.Column("approval_state", sa.String(16), nullable=False, index=True),
        sa.Column("approved_by", sa.String(64), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predecessor", sa.String(64), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "strategy_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("setup_family", sa.String(64), nullable=False, index=True),
        sa.Column("permitted_instruments", sa.JSON(), nullable=False),
        sa.Column("parameter_set_hash", sa.String(80), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("proposed_by", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )
    op.create_table(
        "promotion_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("candidate_id", sa.String(64), sa.ForeignKey("strategy_candidates.id"),
                  nullable=False, index=True),
        sa.Column("from_state", sa.String(16), nullable=False),
        sa.Column("to_state", sa.String(16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_for", sa.JSON(), nullable=False),
        sa.Column("evidence_against", sa.JSON(), nullable=False),
        sa.Column("decided_by", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("rollback_target", sa.String(16), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("promotion_decisions")
    op.drop_table("strategy_candidates")
    op.drop_table("policy_versions")
