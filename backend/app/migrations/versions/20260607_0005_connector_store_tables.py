"""document connector settings and store runtime tables

Revision ID: 20260607_0005
Revises: 20260607_0004
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0005"
down_revision = "20260607_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_method_state_rel (
          provider TEXT NOT NULL,
          method TEXT NOT NULL,
          schedule TEXT NOT NULL,
          last_run_at TEXT NULL,
          last_success_at TEXT NULL,
          last_error_at TEXT NULL,
          last_error TEXT NOT NULL DEFAULT '',
          fail_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'ok',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (provider, method)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_method_state_tenant_rel (
          organization_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          method TEXT NOT NULL,
          schedule TEXT NOT NULL,
          last_run_at TEXT NULL,
          last_success_at TEXT NULL,
          last_error_at TEXT NULL,
          last_error TEXT NOT NULL DEFAULT '',
          fail_count INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'ok',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, provider, method)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_provider_settings_rel (
          provider TEXT NOT NULL,
          setting_key TEXT NOT NULL,
          setting_value TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (provider, setting_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_provider_settings_tenant_rel (
          organization_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          setting_key TEXT NOT NULL,
          setting_value TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, provider, setting_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_import_stores_rel (
          provider TEXT NOT NULL,
          store_id TEXT NOT NULL,
          title TEXT NOT NULL,
          business_id TEXT NULL,
          client_id TEXT NULL,
          api_key TEXT NULL,
          token TEXT NULL,
          auth_mode TEXT NULL,
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          export_enabled BOOLEAN NOT NULL DEFAULT TRUE,
          notes TEXT NULL,
          last_check_at TEXT NULL,
          last_check_status TEXT NULL,
          last_check_error TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL,
          PRIMARY KEY (provider, store_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connector_import_stores_tenant_rel (
          organization_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          store_id TEXT NOT NULL,
          title TEXT NOT NULL,
          business_id TEXT NULL,
          client_id TEXT NULL,
          api_key TEXT NULL,
          token TEXT NULL,
          auth_mode TEXT NULL,
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          export_enabled BOOLEAN NOT NULL DEFAULT TRUE,
          notes TEXT NULL,
          last_check_at TEXT NULL,
          last_check_status TEXT NULL,
          last_check_error TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL,
          PRIMARY KEY (organization_id, provider, store_id)
        )
        """
    )
    op.execute("ALTER TABLE connector_import_stores_rel ADD COLUMN IF NOT EXISTS export_enabled BOOLEAN NOT NULL DEFAULT TRUE")
    op.execute(
        "ALTER TABLE connector_import_stores_tenant_rel ADD COLUMN IF NOT EXISTS export_enabled BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_connector_import_stores_rel_provider
          ON connector_import_stores_rel(provider)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_connector_import_stores_tenant_rel_provider
          ON connector_import_stores_tenant_rel(organization_id, provider)
        """
    )


def downgrade() -> None:
    # These tables contain connector configuration and selected store state.
    # Do not drop production connector data from a downgrade.
    pass
