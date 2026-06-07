"""document attribute value reference runtime tables

Revision ID: 20260607_0009
Revises: 20260607_0008
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0009"
down_revision = "20260607_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_value_refs_rel (
          catalog_category_id TEXT NOT NULL,
          catalog_name_key TEXT NOT NULL,
          catalog_name TEXT NOT NULL,
          param_group TEXT NOT NULL DEFAULT '',
          attribute_id TEXT NULL,
          dict_id TEXT NULL,
          value_type TEXT NULL,
          confirmed BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_provider_category_id TEXT NULL,
          yandex_param_id TEXT NULL,
          yandex_param_name TEXT NULL,
          yandex_kind TEXT NULL,
          yandex_allowed_values TEXT[] NULL,
          yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_provider_category_id TEXT NULL,
          ozon_param_id TEXT NULL,
          ozon_param_name TEXT NULL,
          ozon_kind TEXT NULL,
          ozon_allowed_values TEXT[] NULL,
          ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
          rows_count INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (catalog_category_id, catalog_name_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_value_refs_tenant_rel (
          organization_id TEXT NOT NULL,
          catalog_category_id TEXT NOT NULL,
          catalog_name_key TEXT NOT NULL,
          catalog_name TEXT NOT NULL,
          param_group TEXT NOT NULL DEFAULT '',
          attribute_id TEXT NULL,
          dict_id TEXT NULL,
          value_type TEXT NULL,
          confirmed BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_provider_category_id TEXT NULL,
          yandex_param_id TEXT NULL,
          yandex_param_name TEXT NULL,
          yandex_kind TEXT NULL,
          yandex_allowed_values TEXT[] NULL,
          yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
          yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_provider_category_id TEXT NULL,
          ozon_param_id TEXT NULL,
          ozon_param_name TEXT NULL,
          ozon_kind TEXT NULL,
          ozon_allowed_values TEXT[] NULL,
          ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
          ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
          rows_count INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, catalog_category_id, catalog_name_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attribute_value_refs_rel_category
          ON attribute_value_refs_rel(catalog_category_id, catalog_name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attribute_value_refs_tenant_rel_category
          ON attribute_value_refs_tenant_rel(organization_id, catalog_category_id, catalog_name)
        """
    )


def downgrade() -> None:
    # These tables contain reviewed value/reference metadata for category
    # parameters. Do not drop production mapping state from a downgrade.
    pass
