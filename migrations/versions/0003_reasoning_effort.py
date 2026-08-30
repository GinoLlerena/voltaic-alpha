"""Record the reasoning effort a model call ran at

The effort level changes the output, so a decision made at `high` is not
reproducible from a record that does not say so. The column is nullable and is
not back-filled: rows written before it existed ran at whatever the provider
defaulted to that day, and writing a guess into them would make an unrecorded
setting indistinguishable from a recorded one - the same failure as storing
`false` for a rule that could not be evaluated.

Revision ID: 0003_reasoning_effort
Revises: 0002_learning_capture
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_reasoning_effort"
down_revision = "0002_learning_capture"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("model_calls") as batch:
        batch.add_column(sa.Column("reasoning_effort", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("model_calls") as batch:
        batch.drop_column("reasoning_effort")
