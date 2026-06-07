"""document template runtime tables

Revision ID: 20260607_0011
Revises: 20260607_0010
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0011"
down_revision = "20260607_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS templates_rel (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          category_id TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL,
          meta_json JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS templates_tenant_rel (
          organization_id TEXT NOT NULL,
          id TEXT NOT NULL,
          name TEXT NOT NULL,
          category_id TEXT NULL,
          created_at TEXT NULL,
          updated_at TEXT NULL,
          meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY (organization_id, id)
        )
        """
    )
    op.execute("ALTER TABLE templates_rel ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("ALTER TABLE templates_tenant_rel ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb")
    op.execute("CREATE INDEX IF NOT EXISTS idx_templates_rel_category ON templates_rel(category_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_templates_tenant_rel_category ON templates_tenant_rel(organization_id, category_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS template_attributes_rel (
          template_id TEXT NOT NULL,
          attr_id TEXT NOT NULL,
          name TEXT NOT NULL,
          code TEXT NOT NULL,
          attr_type TEXT NOT NULL,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          scope TEXT NOT NULL DEFAULT 'common',
          attribute_id TEXT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          is_locked BOOLEAN NOT NULL DEFAULT FALSE,
          options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY (template_id, attr_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS template_attributes_tenant_rel (
          organization_id TEXT NOT NULL,
          template_id TEXT NOT NULL,
          attr_id TEXT NOT NULL,
          name TEXT NOT NULL,
          code TEXT NOT NULL,
          attr_type TEXT NOT NULL,
          is_required BOOLEAN NOT NULL DEFAULT FALSE,
          scope TEXT NOT NULL DEFAULT 'common',
          attribute_id TEXT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          is_locked BOOLEAN NOT NULL DEFAULT FALSE,
          options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          PRIMARY KEY (organization_id, template_id, attr_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_template_attributes_rel_template_position
          ON template_attributes_rel(template_id, position, code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_template_attributes_tenant_rel_template_position
          ON template_attributes_tenant_rel(organization_id, template_id, position, code)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_template_links_rel (
          category_id TEXT NOT NULL,
          template_id TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (category_id, template_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_template_links_tenant_rel (
          organization_id TEXT NOT NULL,
          category_id TEXT NOT NULL,
          template_id TEXT NOT NULL,
          position INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (organization_id, category_id, template_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_category_template_links_rel_category_position
          ON category_template_links_rel(category_id, position)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_category_template_links_tenant_rel_category_position
          ON category_template_links_tenant_rel(organization_id, category_id, position)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_template_resolution_rel (
          category_id TEXT PRIMARY KEY,
          template_id TEXT NULL,
          template_name TEXT NULL,
          source_category_id TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS category_template_resolution_tenant_rel (
          organization_id TEXT NOT NULL,
          category_id TEXT NOT NULL,
          template_id TEXT NULL,
          template_name TEXT NULL,
          source_category_id TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, category_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_category_template_resolution_tenant_rel_category
          ON category_template_resolution_tenant_rel(organization_id, category_id)
        """
    )


def downgrade() -> None:
    # These tables contain production info-models and category-template
    # resolution state. Do not drop them from a downgrade.
    pass
