"""document attribute provider binding runtime tables

Revision ID: 20260607_0006
Revises: 20260607_0005
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0006"
down_revision = "20260607_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_provider_bindings_rel (
          catalog_category_id TEXT NOT NULL,
          row_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          provider_param_id TEXT NULL,
          provider_param_name TEXT NULL,
          provider_kind TEXT NULL,
          provider_values TEXT[] NULL,
          provider_required BOOLEAN NOT NULL DEFAULT FALSE,
          provider_export BOOLEAN NOT NULL DEFAULT FALSE,
          match_source TEXT NULL,
          match_confidence DOUBLE PRECISION NULL,
          match_reason TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (catalog_category_id, row_id, provider, position)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS attribute_provider_bindings_tenant_rel (
          organization_id TEXT NOT NULL,
          catalog_category_id TEXT NOT NULL,
          row_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          provider_param_id TEXT NULL,
          provider_param_name TEXT NULL,
          provider_kind TEXT NULL,
          provider_values TEXT[] NULL,
          provider_required BOOLEAN NOT NULL DEFAULT FALSE,
          provider_export BOOLEAN NOT NULL DEFAULT FALSE,
          match_source TEXT NULL,
          match_confidence DOUBLE PRECISION NULL,
          match_reason TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, catalog_category_id, row_id, provider, position)
        )
        """
    )
    for table_name in ("attribute_provider_bindings_rel", "attribute_provider_bindings_tenant_rel"):
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS match_source TEXT NULL")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS match_confidence DOUBLE PRECISION NULL")
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS match_reason TEXT NULL")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_attribute_provider_bindings_tenant_rel_lookup
          ON attribute_provider_bindings_tenant_rel(organization_id, catalog_category_id, row_id, provider)
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.attribute_mappings_rel') IS NOT NULL THEN
            ALTER TABLE attribute_mappings_rel ADD COLUMN IF NOT EXISTS yandex_bindings_json JSONB NULL;
            ALTER TABLE attribute_mappings_rel ADD COLUMN IF NOT EXISTS ozon_bindings_json JSONB NULL;

            INSERT INTO attribute_provider_bindings_rel (
              catalog_category_id, row_id, provider, position,
              provider_param_id, provider_param_name, provider_kind, provider_values, provider_required, provider_export,
              updated_at
            )
            SELECT
              catalog_category_id, row_id, 'yandex_market', 0,
              yandex_param_id, yandex_param_name, yandex_kind, yandex_values, yandex_required, yandex_export,
              NOW()
            FROM attribute_mappings_rel
            WHERE COALESCE(yandex_param_id, '') <> '' OR COALESCE(yandex_param_name, '') <> ''
            ON CONFLICT DO NOTHING;

            INSERT INTO attribute_provider_bindings_rel (
              catalog_category_id, row_id, provider, position,
              provider_param_id, provider_param_name, provider_kind, provider_values, provider_required, provider_export,
              updated_at
            )
            SELECT
              catalog_category_id, row_id, 'ozon', 0,
              ozon_param_id, ozon_param_name, ozon_kind, ozon_values, ozon_required, ozon_export,
              NOW()
            FROM attribute_mappings_rel
            WHERE COALESCE(ozon_param_id, '') <> '' OR COALESCE(ozon_param_name, '') <> ''
            ON CONFLICT DO NOTHING;
          END IF;

          IF to_regclass('public.attribute_mappings_tenant_rel') IS NOT NULL THEN
            ALTER TABLE attribute_mappings_tenant_rel ADD COLUMN IF NOT EXISTS yandex_bindings_json JSONB NULL;
            ALTER TABLE attribute_mappings_tenant_rel ADD COLUMN IF NOT EXISTS ozon_bindings_json JSONB NULL;

            INSERT INTO attribute_provider_bindings_tenant_rel (
              organization_id, catalog_category_id, row_id, provider, position,
              provider_param_id, provider_param_name, provider_kind, provider_values, provider_required, provider_export,
              updated_at
            )
            SELECT
              organization_id, catalog_category_id, row_id, 'yandex_market', 0,
              yandex_param_id, yandex_param_name, yandex_kind, yandex_values, yandex_required, yandex_export,
              NOW()
            FROM attribute_mappings_tenant_rel
            WHERE COALESCE(yandex_param_id, '') <> '' OR COALESCE(yandex_param_name, '') <> ''
            ON CONFLICT DO NOTHING;

            INSERT INTO attribute_provider_bindings_tenant_rel (
              organization_id, catalog_category_id, row_id, provider, position,
              provider_param_id, provider_param_name, provider_kind, provider_values, provider_required, provider_export,
              updated_at
            )
            SELECT
              organization_id, catalog_category_id, row_id, 'ozon', 0,
              ozon_param_id, ozon_param_name, ozon_kind, ozon_values, ozon_required, ozon_export,
              NOW()
            FROM attribute_mappings_tenant_rel
            WHERE COALESCE(ozon_param_id, '') <> '' OR COALESCE(ozon_param_name, '') <> ''
            ON CONFLICT DO NOTHING;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # These tables contain reviewed marketplace parameter bindings. Do not
    # drop production mapping state from a downgrade.
    pass
