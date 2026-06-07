"""document auth and control plane runtime tables

Revision ID: 20260607_0004
Revises: 20260607_0003
Create Date: 2026-06-07
"""

from __future__ import annotations

from alembic import op

revision = "20260607_0004"
down_revision = "20260607_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
          id TEXT PRIMARY KEY,
          code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          description TEXT NULL,
          pages JSONB NOT NULL DEFAULT '[]'::jsonb,
          actions JSONB NOT NULL DEFAULT '[]'::jsonb,
          is_system BOOLEAN NOT NULL DEFAULT FALSE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY,
          login TEXT NOT NULL DEFAULT '',
          email TEXT NOT NULL DEFAULT '',
          password_hash TEXT NOT NULL DEFAULT '',
          password_salt TEXT NOT NULL DEFAULT '',
          name TEXT NOT NULL,
          role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
          is_active BOOLEAN NOT NULL DEFAULT TRUE,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_login_at TIMESTAMPTZ NULL,
          last_login_ip TEXT NULL,
          last_user_agent TEXT NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_login ON users ((lower(login)))")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email_non_empty ON users ((lower(email))) WHERE email <> ''")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
          id TEXT PRIMARY KEY,
          slug TEXT NOT NULL,
          name TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          tenant_status TEXT NULL,
          provisioning_error TEXT NULL,
          schema_version TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_lower_slug ON organizations ((lower(slug)))")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_members (
          id TEXT PRIMARY KEY,
          organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          org_role_code TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_members_unique
          ON organization_members (organization_id, user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organization_invites (
          id TEXT PRIMARY KEY,
          organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
          email TEXT NOT NULL,
          org_role_code TEXT NOT NULL,
          token_hash TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          expires_at TIMESTAMPTZ NOT NULL,
          created_by_user_id TEXT NOT NULL REFERENCES users(id),
          accepted_by_user_id TEXT NULL REFERENCES users(id),
          accepted_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_invites_token_hash ON organization_invites (token_hash)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_organization_invites_org_email
          ON organization_invites (organization_id, lower(email))
        """
    )


def downgrade() -> None:
    # These tables contain production users, roles, organizations, membership
    # and invite state. Do not drop them from a downgrade.
    pass
