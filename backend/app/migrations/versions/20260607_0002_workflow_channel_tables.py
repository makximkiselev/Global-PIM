"""document workflow and channel link runtime tables

Revision ID: 20260607_0002
Revises: 20260607_0001
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0002"
down_revision = "20260607_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pim_channel_links (
          organization_id TEXT NOT NULL DEFAULT 'org_default',
          link_id TEXT NOT NULL,
          scope TEXT NOT NULL,
          entity_type TEXT NOT NULL,
          entity_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          url TEXT NOT NULL DEFAULT '',
          external_id TEXT NOT NULL DEFAULT '',
          title TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT '',
          score DOUBLE PRECISION NULL,
          source TEXT NOT NULL DEFAULT '',
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, link_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pim_channel_links_entity
          ON pim_channel_links(organization_id, scope, entity_type, entity_id, provider, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pim_channel_links_provider_url
          ON pim_channel_links(organization_id, provider, url)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pim_workflow_runs (
          organization_id TEXT NOT NULL DEFAULT 'org_default',
          workflow TEXT NOT NULL,
          run_id TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT '',
          payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          started_at TEXT NULL,
          finished_at TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organization_id, workflow, run_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pim_workflow_runs_status
          ON pim_workflow_runs(organization_id, workflow, status, updated_at DESC)
        """
    )


def downgrade() -> None:
    # These tables existed before Alembic and may contain production workflow
    # history, competitor links, and moderation decisions. Do not drop them.
    pass
