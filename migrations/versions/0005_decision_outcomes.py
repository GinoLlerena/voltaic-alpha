"""Persist review jobs and decision outcomes

`CIIP-008`. The architecture had an in-memory `DecisionOutcome` describing what
the workflow decided; nothing recorded what was observable afterwards. Without
it there is no honest basis for any later claim about the policy, which is why
`CIIP-009` onward depend on this.

Two tables, and the split is the point. A `review_jobs` row is the question,
created with the decision and resolved only once its horizon has elapsed in
completed sessions. A `decision_outcomes` row is the answer, written once.
Neither touches `decisions`: enrichment is append-only, so the record of what
was decided cannot drift toward what happened.

Not back-filled. Decisions recorded before this revision have no review jobs,
and inventing them now would date a question to a moment nobody asked it.

Revision ID: 0005_decision_outcomes
Revises: 0004_worker_events
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_decision_outcomes"
down_revision = "0004_worker_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("decision_id", sa.String(64), sa.ForeignKey("decisions.id"),
                  nullable=False, index=True),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, index=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("decision_id", "horizon", name="uq_review_job_horizon"),
    )
    op.create_table(
        "decision_outcomes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("decision_id", sa.String(64), sa.ForeignKey("decisions.id"),
                  nullable=False, index=True),
        sa.Column("review_job_id", sa.String(64), sa.ForeignKey("review_jobs.id"),
                  nullable=False, unique=True),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("horizon_sessions", sa.Integer(), nullable=False),
        sa.Column("outcome_kind", sa.String(16), nullable=False, index=True),
        sa.Column("observed_snapshot_id", sa.String(128), nullable=False),
        sa.Column("observed_source_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sessions_elapsed", sa.Integer(), nullable=False),
        sa.Column("underlying_at_decision", sa.Numeric(18, 6), nullable=False),
        sa.Column("underlying_at_horizon", sa.Numeric(18, 6), nullable=False),
        sa.Column("underlying_change", sa.Numeric(18, 6), nullable=False),
        sa.Column("direction_agreed", sa.Boolean(), nullable=True),
        sa.Column("realized", sa.Numeric(18, 6), nullable=True),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("decision_id", "horizon", name="uq_decision_outcome_horizon"),
    )


def downgrade() -> None:
    op.drop_table("decision_outcomes")
    op.drop_table("review_jobs")
