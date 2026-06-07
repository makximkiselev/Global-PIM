"""document catalog category and marketplace mapping tables

Revision ID: 20260607_0007
Revises: 20260607_0006
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0007"
down_revision = "20260607_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_nodes_rel (
          id TEXT PRIMARY KEY,
          parent_id TEXT NULL,
          name TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          template_id TEXT NULL,
          products_count INTEGER NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_nodes_rel_parent_position
          ON catalog_nodes_rel(parent_id, position)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_mappings_rel (
          catalog_category_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          provider_category_id TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (catalog_category_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_mappings_tenant_rel (
          organization_id TEXT NOT NULL,
          catalog_category_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          provider_category_id TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, catalog_category_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_category_mappings_rel_provider
          ON category_mappings_rel(provider, provider_category_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_category_mappings_tenant_rel_provider
          ON category_mappings_tenant_rel(organization_id, provider, provider_category_id)
        """
    )


def downgrade() -> None:
    # These tables contain imported catalog structure and reviewed marketplace
    # category bindings. Do not drop production mapping state from a downgrade.
    pass
