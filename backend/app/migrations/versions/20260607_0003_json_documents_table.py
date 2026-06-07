"""document json_documents runtime table

Revision ID: 20260607_0003
Revises: 20260607_0002
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0003"
down_revision = "20260607_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS json_documents (
          path TEXT PRIMARY KEY,
          payload JSONB NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    # This table existed before Alembic and contains production JSON document
    # state. Do not drop it from a downgrade.
    pass
