CREATE TABLE IF NOT EXISTS platform_users (
  id TEXT PRIMARY KEY,
  legacy_user_id TEXT NULL,
  email TEXT NOT NULL,
  password_hash TEXT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_login_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_users_lower_email
  ON platform_users ((lower(email)));

CREATE TABLE IF NOT EXISTS platform_roles (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS platform_user_roles (
  platform_user_id TEXT NOT NULL REFERENCES platform_users(id) ON DELETE CASCADE,
  platform_role_id TEXT NOT NULL REFERENCES platform_roles(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (platform_user_id, platform_role_id)
);

CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  slug TEXT NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organizations_lower_slug
  ON organizations ((lower(slug)));

CREATE TABLE IF NOT EXISTS organization_members (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  platform_user_id TEXT NOT NULL REFERENCES platform_users(id) ON DELETE CASCADE,
  org_role_code TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_members_unique
  ON organization_members (organization_id, platform_user_id);

CREATE TABLE IF NOT EXISTS organization_invites (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  org_role_code TEXT NOT NULL,
  token_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  expires_at TIMESTAMPTZ NOT NULL,
  created_by_user_id TEXT NOT NULL REFERENCES platform_users(id),
  accepted_by_user_id TEXT NULL REFERENCES platform_users(id),
  accepted_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_invites_token_hash
  ON organization_invites (token_hash);

CREATE INDEX IF NOT EXISTS idx_organization_invites_org_email
  ON organization_invites (organization_id, lower(email));

CREATE TABLE IF NOT EXISTS tenant_registry (
  organization_id TEXT PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  db_host TEXT NOT NULL,
  db_port INTEGER NOT NULL,
  db_name TEXT NOT NULL,
  db_user TEXT NOT NULL,
  db_secret_ref TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  schema_version TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_provisioning_jobs (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  attempt INTEGER NOT NULL DEFAULT 0,
  error TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO platform_roles (id, code, name, description, created_at, updated_at)
VALUES
  ('platform_role_developer', 'developer', 'Developer', 'Глобальный доступ ко всем организациям.', NOW(), NOW()),
  ('platform_role_admin', 'platform_admin', 'Platform Admin', 'Управление control-plane сущностями.', NOW(), NOW()),
  ('platform_role_support', 'platform_support', 'Platform Support', 'Поддержка и диагностика организаций.', NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET code = EXCLUDED.code,
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    updated_at = NOW();

INSERT INTO organizations (id, slug, name, status, created_at, updated_at)
VALUES ('org_default', 'default', 'Default organization', 'active', NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET slug = EXCLUDED.slug,
    name = EXCLUDED.name,
    updated_at = NOW();
