"""baseline existing runtime schema

Revision ID: 20260607_0001
Revises:
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op  # noqa: F401

revision = "20260607_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing production tables were created by legacy runtime DDL.
    # This baseline intentionally records the migration starting point only.
    pass


def downgrade() -> None:
    pass
