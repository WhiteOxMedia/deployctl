"""create readiness table

Revision ID: 002
Revises: 001
Create Date: 2026-10-23

The readiness table stores the probe evaluation results and latest readiness
state per deployment. It carries the explicit `observed_at`, `scope_id`, and
`source_id` columns that the readiness controller now forwards from the probe
evaluation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "readiness",
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("details", sa.String(), nullable=True),
        sa.Column(
            "timestamp",
            sa.String(),
            nullable=False,
            server_default=sa.text("datetime('now')"),
        ),
        sa.Column(
            "observed_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("datetime('now')"),
        ),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("deployment_id"),
    )


def downgrade() -> None:
    op.drop_table("readiness")
