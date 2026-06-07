"""document product group and variant runtime tables

Revision ID: 20260607_0013
Revises: 20260607_0012
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0013"
down_revision = "20260607_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_groups_rel (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_group_variant_params_rel (
          group_id TEXT NOT NULL,
          param_id TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (group_id, param_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_product_group_variant_params_rel_group
          ON product_group_variant_params_rel(group_id, position)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_variants_rel (
          id TEXT PRIMARY KEY,
          product_id TEXT NOT NULL,
          sku TEXT NULL,
          sku_pim TEXT NULL,
          sku_gt TEXT NULL,
          title TEXT NULL,
          links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_product_variants_rel_product ON product_variants_rel(product_id)")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_product_variants_rel_sku
          ON product_variants_rel(sku)
          WHERE COALESCE(sku, '') <> ''
        """
    )


def downgrade() -> None:
    # These tables contain production product family and SKU variant state. Do
    # not drop them from a downgrade.
    pass
