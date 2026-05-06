CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  login TEXT NOT NULL,
  email TEXT NOT NULL,
  password_hash TEXT NULL,
  password_salt TEXT NULL,
  name TEXT NOT NULL,
  role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_login
  ON users ((lower(login)));

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email
  ON users ((lower(email)));

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
);

CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  tenant_status TEXT NOT NULL DEFAULT 'active',
  provisioning_error TEXT NULL,
  schema_version TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_lower_slug
  ON organizations ((lower(slug)));

CREATE TABLE IF NOT EXISTS organization_members (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  org_role_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_members_unique
  ON organization_members (organization_id, user_id);

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
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_invites_token_hash
  ON organization_invites (token_hash);

CREATE INDEX IF NOT EXISTS idx_organization_invites_org_email
  ON organization_invites (organization_id, lower(email));

INSERT INTO organizations (id, slug, name, status, tenant_status, created_at, updated_at)
VALUES ('org_default', 'default', 'Global Trade', 'active', 'active', NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET slug = EXCLUDED.slug,
    name = EXCLUDED.name,
    status = EXCLUDED.status,
    tenant_status = EXCLUDED.tenant_status,
    updated_at = NOW();
