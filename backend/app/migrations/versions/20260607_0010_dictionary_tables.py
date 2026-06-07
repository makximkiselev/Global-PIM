"""document dictionary runtime tables

Revision ID: 20260607_0010
Revises: 20260607_0009
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0010"
down_revision = "20260607_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionaries_rel (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          code TEXT NOT NULL,
          attr_id TEXT NOT NULL,
          attr_type TEXT NOT NULL DEFAULT 'select',
          scope TEXT NOT NULL DEFAULT 'both',
          is_service BOOLEAN NOT NULL DEFAULT FALSE,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          param_group TEXT NULL,
          template_layer TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionaries_tenant_rel (
          organization_id TEXT NOT NULL,
          id TEXT NOT NULL,
          title TEXT NOT NULL,
          code TEXT NOT NULL,
          attr_id TEXT NOT NULL,
          attr_type TEXT NOT NULL DEFAULT 'select',
          scope TEXT NOT NULL DEFAULT 'both',
          is_service BOOLEAN NOT NULL DEFAULT FALSE,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          param_group TEXT NULL,
          template_layer TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL,
          PRIMARY KEY (organization_id, id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_code ON dictionaries_rel(code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dictionaries_tenant_rel_code ON dictionaries_tenant_rel(organization_id, code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_attr_id ON dictionaries_rel(attr_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_dictionaries_tenant_rel_attr_id ON dictionaries_tenant_rel(organization_id, attr_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_values_rel (
          dict_id TEXT NOT NULL,
          value_key TEXT NOT NULL,
          value_text TEXT NOT NULL,
          value_count INTEGER NOT NULL DEFAULT 0,
          last_seen TEXT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (dict_id, value_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_values_tenant_rel (
          organization_id TEXT NOT NULL,
          dict_id TEXT NOT NULL,
          value_key TEXT NOT NULL,
          value_text TEXT NOT NULL,
          value_count INTEGER NOT NULL DEFAULT 0,
          last_seen TEXT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (organization_id, dict_id, value_key)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dictionary_values_rel_dict_position
          ON dictionary_values_rel(dict_id, position, value_text)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dictionary_values_tenant_rel_dict_position
          ON dictionary_values_tenant_rel(organization_id, dict_id, position, value_text)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_value_sources_rel (
          dict_id TEXT NOT NULL,
          value_key TEXT NOT NULL,
          source_name TEXT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (dict_id, value_key, source_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_value_sources_tenant_rel (
          organization_id TEXT NOT NULL,
          dict_id TEXT NOT NULL,
          value_key TEXT NOT NULL,
          source_name TEXT NOT NULL,
          source_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (organization_id, dict_id, value_key, source_name)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_aliases_rel (
          dict_id TEXT NOT NULL,
          alias_key TEXT NOT NULL,
          canonical_value TEXT NOT NULL,
          PRIMARY KEY (dict_id, alias_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_aliases_tenant_rel (
          organization_id TEXT NOT NULL,
          dict_id TEXT NOT NULL,
          alias_key TEXT NOT NULL,
          canonical_value TEXT NOT NULL,
          PRIMARY KEY (organization_id, dict_id, alias_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_provider_refs_rel (
          dict_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          provider_param_id TEXT NULL,
          provider_param_name TEXT NULL,
          kind TEXT NULL,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          allowed_values TEXT[] NULL,
          PRIMARY KEY (dict_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_provider_refs_tenant_rel (
          organization_id TEXT NOT NULL,
          dict_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          provider_param_id TEXT NULL,
          provider_param_name TEXT NULL,
          kind TEXT NULL,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          allowed_values TEXT[] NULL,
          PRIMARY KEY (organization_id, dict_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_export_maps_rel (
          dict_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          canonical_key TEXT NOT NULL,
          provider_value TEXT NOT NULL,
          PRIMARY KEY (dict_id, provider, canonical_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dictionary_export_maps_tenant_rel (
          organization_id TEXT NOT NULL,
          dict_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          canonical_key TEXT NOT NULL,
          provider_value TEXT NOT NULL,
          PRIMARY KEY (organization_id, dict_id, provider, canonical_key)
        )
        """
    )


def downgrade() -> None:
    # These tables contain normalized parameter values and export mappings. Do
    # not drop production dictionary state from a downgrade.
    pass
