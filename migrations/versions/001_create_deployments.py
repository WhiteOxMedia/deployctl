"""create deployments table

Revision ID: 001
Revises:
Create Date: 2026-10-22

"""

from __future__ import annotations

from typing import Literal

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "deployments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("artifact_ref", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column(
            "created_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("datetime('now')"),
        ),
        sa.Column(
            "updated_at",
            sa.String(),
            nullable=False,
            server_default=sa.text("datetime('now')"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("deployments")
