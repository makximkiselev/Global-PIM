"""document legacy attribute mapping runtime tables

Revision ID: 20260607_0008
Revises: 20260607_0007
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0008"
down_revision = "20260607_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_mappings_rel (
          catalog_category_id TEXT NOT NULL,
          row_id TEXT NOT NULL,
          catalog_name TEXT NOT NULL,
          param_group TEXT NOT NULL DEFAULT '',
          confirmed BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_param_id TEXT NULL,
          yandex_param_name TEXT NULL,
          yandex_kind TEXT NULL,
          yandex_values TEXT[] NULL,
          yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_bindings_json JSONB NULL,
          ozon_param_id TEXT NULL,
          ozon_param_name TEXT NULL,
          ozon_kind TEXT NULL,
          ozon_values TEXT[] NULL,
          ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_bindings_json JSONB NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (catalog_category_id, row_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_mappings_tenant_rel (
          organization_id TEXT NOT NULL,
          catalog_category_id TEXT NOT NULL,
          row_id TEXT NOT NULL,
          catalog_name TEXT NOT NULL,
          param_group TEXT NOT NULL DEFAULT '',
          confirmed BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_param_id TEXT NULL,
          yandex_param_name TEXT NULL,
          yandex_kind TEXT NULL,
          yandex_values TEXT[] NULL,
          yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_bindings_json JSONB NULL,
          ozon_param_id TEXT NULL,
          ozon_param_name TEXT NULL,
          ozon_kind TEXT NULL,
          ozon_values TEXT[] NULL,
          ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_bindings_json JSONB NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, catalog_category_id, row_id)
        )
        """
    )
    for table_name in ("attribute_mappings_rel", "attribute_mappings_tenant_rel"):
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS yandex_bindings_json JSONB NULL")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS ozon_bindings_json JSONB NULL")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attribute_mappings_rel_category
          ON attribute_mappings_rel(catalog_category_id, catalog_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attribute_mappings_tenant_rel_category
          ON attribute_mappings_tenant_rel(organization_id, catalog_category_id, catalog_name)
        """
    )


def downgrade() -> None:
    # These tables contain reviewed info-model parameter mappings. Do not drop
    # production mapping state from a downgrade.
    pass
