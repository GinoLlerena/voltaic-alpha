"""h0.1 baseline

The schema as `create_schema` builds it from the model metadata: runs, market
snapshots, signals, evidence packs, model calls, theses, spread candidates, risk
decisions, decisions, order intents, prepared requests, broker orders, fills,
positions, incidents, worker leases, and audit events.

This revision is deliberately a no-op marker rather than a transcription of
those seventeen tables. The metadata is the source of truth for a *new*
database - `create_schema` creates it and stamps this revision - and migrations
exist to move an *existing* database forward, which is what the hosted
PostgreSQL needs. The consequence, stated plainly rather than discovered later:
`alembic upgrade head` against a genuinely empty database does not build the
schema. Use `create_schema`, which stamps, and then upgrade.

Revision ID: 0001_h0_baseline
Revises:
"""

from __future__ import annotations

revision = "0001_h0_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
