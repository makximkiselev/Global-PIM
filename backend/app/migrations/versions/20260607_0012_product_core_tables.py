"""document product core runtime tables

Revision ID: 20260607_0012
Revises: 20260607_0011
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0012"
down_revision = "20260607_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS products_rel (
          id TEXT PRIMARY KEY,
          category_id TEXT NOT NULL,
          product_type TEXT NOT NULL DEFAULT 'single',
          status TEXT NOT NULL DEFAULT 'draft',
          title TEXT NOT NULL,
          sku_pim TEXT NULL,
          sku_gt TEXT NULL,
          group_id TEXT NULL,
          selected_params TEXT[] NOT NULL DEFAULT '{}'::text[],
          feature_params TEXT[] NOT NULL DEFAULT '{}'::text[],
          exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TEXT NULL,
          updated_at TEXT NULL
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_rel_category ON products_rel(category_id, title)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_rel_sku_gt ON products_rel(sku_gt)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_rel_sku_pim ON products_rel(sku_pim)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_products_rel_group ON products_rel(group_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_product_registry_rel (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          category_id TEXT NOT NULL,
          sku_pim TEXT NULL,
          sku_gt TEXT NULL,
          group_id TEXT NULL,
          preview_url TEXT NULL,
          exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at TEXT NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_category
          ON catalog_product_registry_rel(category_id, title)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_sku_gt ON catalog_product_registry_rel(sku_gt)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_product_counts_rel (
          category_id TEXT PRIMARY KEY,
          products_count INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_marketplace_status_rel (
          product_id TEXT PRIMARY KEY,
          yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
          ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS product_marketplace_status_tenant_rel (
          organization_id TEXT NOT NULL,
          product_id TEXT NOT NULL,
          yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
          ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, product_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_product_page_rel (
          product_id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          category_id TEXT NOT NULL,
          category_path TEXT NOT NULL DEFAULT '',
          sku_pim TEXT NULL,
          sku_gt TEXT NULL,
          group_id TEXT NULL,
          group_name TEXT NULL,
          template_id TEXT NULL,
          template_name TEXT NULL,
          template_source_category_id TEXT NULL,
          yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
          ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
          preview_url TEXT NULL,
          exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_product_page_tenant_rel (
          organization_id TEXT NOT NULL,
          product_id TEXT NOT NULL,
          title TEXT NOT NULL,
          category_id TEXT NOT NULL,
          category_path TEXT NOT NULL DEFAULT '',
          sku_pim TEXT NULL,
          sku_gt TEXT NULL,
          group_id TEXT NULL,
          group_name TEXT NULL,
          template_id TEXT NULL,
          template_name TEXT NULL,
          template_source_category_id TEXT NULL,
          yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
          ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
          preview_url TEXT NULL,
          exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, product_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_category ON catalog_product_page_rel(category_id, title)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_group ON catalog_product_page_rel(group_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_template ON catalog_product_page_rel(template_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_product_marketplace_status_tenant_rel_org
          ON product_marketplace_status_tenant_rel(organization_id, product_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_category
          ON catalog_product_page_tenant_rel(organization_id, category_id, title)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_group
          ON catalog_product_page_tenant_rel(organization_id, group_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_template
          ON catalog_product_page_tenant_rel(organization_id, template_id)
        """
    )


def downgrade() -> None:
    # These tables contain production catalog products and materialized product
    # page/export status state. Do not drop them from a downgrade.
    pass
