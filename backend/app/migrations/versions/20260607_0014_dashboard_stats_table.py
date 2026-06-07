"""document dashboard stats runtime table

Revision ID: 20260607_0014
Revises: 20260607_0013
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0014"
down_revision = "20260607_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_stats_rel (
          summary_key TEXT PRIMARY KEY,
          categories_count INTEGER NOT NULL DEFAULT 0,
          products_count INTEGER NOT NULL DEFAULT 0,
          templates_count INTEGER NOT NULL DEFAULT 0,
          connectors_configured INTEGER NOT NULL DEFAULT 0,
          connectors_total INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    # This table contains persisted dashboard summary state. Do not drop it from
    # a downgrade.
    pass
