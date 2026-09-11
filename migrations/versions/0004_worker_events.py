"""Persist worker lifecycle and reconciliation events

`CIIP-I-008`. `audit_events` records what happened to a decision, keyed by its
correlation id, and has nowhere to put what happens to the worker itself:
starting, stopping, losing a lease, reconciling at startup, a tick that raised.
Those are run-scoped and belong to no decision, so they lived only in journald —
which the retention standard caps at thirty days and a reinstall discards.

A product surface showing "what the agent is doing" therefore had nothing
durable to read. The alternative is to synthesise it in the browser, which is
the exact defect this project has spent two analyses criticising elsewhere.

Not back-filled, and deliberately so. Every worker run before this revision
emitted these events to the journal only, and most of those journals are gone
with the host that was released on 9 September. Writing rows for them would make
an unrecorded run indistinguishable from a recorded one.

Revision ID: 0004_worker_events
Revises: 0003_reasoning_effort
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_worker_events"
down_revision = "0003_reasoning_effort"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("runs.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("kind", sa.String(16), nullable=False, index=True),
        sa.Column("event", sa.String(64), nullable=False, index=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_events")
