CREATE TABLE IF NOT EXISTS product_groups_rel (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NULL,
  updated_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS product_group_variant_params_rel (
  group_id TEXT NOT NULL,
  param_id TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (group_id, param_id)
);

CREATE INDEX IF NOT EXISTS idx_product_group_variant_params_rel_group
  ON product_group_variant_params_rel(group_id, position);

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
);

CREATE TABLE IF NOT EXISTS connector_provider_settings_rel (
  provider TEXT NOT NULL,
  setting_key TEXT NOT NULL,
  setting_value TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (provider, setting_key)
);

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
  notes TEXT NULL,
  last_check_at TEXT NULL,
  last_check_status TEXT NULL,
  last_check_error TEXT NULL,
  created_at TEXT NULL,
  updated_at TEXT NULL,
  PRIMARY KEY (provider, store_id)
);

CREATE INDEX IF NOT EXISTS idx_connector_import_stores_rel_provider
  ON connector_import_stores_rel(provider, enabled);
