-- Draft only. Do not run in production without backfill/parity plan.
-- Requires deploy/sql/013_control_plane_foundation.sql because tenant-scoped
-- tables reference organizations(id).
-- Goal: consolidate current PIM relational + json_documents storage into a small
-- set of domain tables that can serve catalog, product, model, mapping,
-- enrichment, connector, and export pages from shared sources.

CREATE TABLE IF NOT EXISTS pim_categories (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  id TEXT NOT NULL,
  parent_id TEXT NULL,
  name TEXT NOT NULL,
  path_ids TEXT[] NOT NULL DEFAULT '{}'::text[],
  path_names TEXT[] NOT NULL DEFAULT '{}'::text[],
  position INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'active',
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, parent_id) REFERENCES pim_categories(organization_id, id) ON DELETE RESTRICT,
  CONSTRAINT chk_pim_categories_summary_object CHECK (jsonb_typeof(summary_json) = 'object'),
  CONSTRAINT chk_pim_categories_meta_object CHECK (jsonb_typeof(meta_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pim_categories_parent_position
  ON pim_categories (organization_id, parent_id, position);

CREATE INDEX IF NOT EXISTS idx_pim_categories_path_gin
  ON pim_categories USING GIN (path_ids);

CREATE INDEX IF NOT EXISTS idx_pim_categories_status
  ON pim_categories (organization_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS pim_products (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  group_id TEXT NULL,
  sku_gt TEXT NULL,
  sku_pim TEXT NULL,
  title TEXT NOT NULL,
  product_type TEXT NOT NULL DEFAULT 'single',
  status TEXT NOT NULL DEFAULT 'draft',
  content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  media_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  relations_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  channel_readiness_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  export_flags_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  competitor_links_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ui_summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, category_id) REFERENCES pim_categories(organization_id, id) ON DELETE RESTRICT,
  CONSTRAINT chk_pim_products_content_object CHECK (jsonb_typeof(content_json) = 'object'),
  CONSTRAINT chk_pim_products_media_object CHECK (jsonb_typeof(media_json) = 'object'),
  CONSTRAINT chk_pim_products_relations_object CHECK (jsonb_typeof(relations_json) = 'object'),
  CONSTRAINT chk_pim_products_channel_readiness_object CHECK (jsonb_typeof(channel_readiness_json) = 'object'),
  CONSTRAINT chk_pim_products_export_flags_object CHECK (jsonb_typeof(export_flags_json) = 'object'),
  CONSTRAINT chk_pim_products_competitor_links_object CHECK (jsonb_typeof(competitor_links_json) = 'object'),
  CONSTRAINT chk_pim_products_ui_summary_object CHECK (jsonb_typeof(ui_summary_json) = 'object'),
  CONSTRAINT chk_pim_products_source_object CHECK (jsonb_typeof(source_json) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pim_products_sku_gt
  ON pim_products (organization_id, sku_gt)
  WHERE COALESCE(sku_gt, '') <> '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_pim_products_sku_pim
  ON pim_products (organization_id, sku_pim)
  WHERE COALESCE(sku_pim, '') <> '';

CREATE INDEX IF NOT EXISTS idx_pim_products_category_title
  ON pim_products (organization_id, category_id, title);

CREATE INDEX IF NOT EXISTS idx_pim_products_category_status_updated
  ON pim_products (organization_id, category_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_pim_products_group
  ON pim_products (organization_id, group_id);

CREATE INDEX IF NOT EXISTS idx_pim_products_content_gin
  ON pim_products USING GIN (content_json);

CREATE TABLE IF NOT EXISTS pim_product_values (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  product_id TEXT NOT NULL,
  field_id TEXT NOT NULL,
  canonical_value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  raw_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence NUMERIC(5, 4) NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  normalized_at TIMESTAMPTZ NULL,
  approved_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, product_id, field_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, product_id) REFERENCES pim_products(organization_id, id) ON DELETE CASCADE,
  CONSTRAINT chk_pim_product_values_canonical_object CHECK (jsonb_typeof(canonical_value_json) = 'object'),
  CONSTRAINT chk_pim_product_values_raw_array CHECK (jsonb_typeof(raw_values_json) = 'array'),
  CONSTRAINT chk_pim_product_values_source_links_array CHECK (jsonb_typeof(source_links_json) = 'array'),
  CONSTRAINT chk_pim_product_values_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_pim_product_values_field
  ON pim_product_values (organization_id, field_id, status);

CREATE INDEX IF NOT EXISTS idx_pim_product_values_value_gin
  ON pim_product_values USING GIN (canonical_value_json);

CREATE INDEX IF NOT EXISTS idx_pim_product_values_status_updated
  ON pim_product_values (organization_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS pim_models (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  source_category_id TEXT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  inheritance_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, category_id) REFERENCES pim_categories(organization_id, id) ON DELETE RESTRICT,
  FOREIGN KEY (organization_id, source_category_id) REFERENCES pim_categories(organization_id, id) ON DELETE RESTRICT,
  CONSTRAINT chk_pim_models_inheritance_object CHECK (jsonb_typeof(inheritance_json) = 'object'),
  CONSTRAINT chk_pim_models_summary_object CHECK (jsonb_typeof(summary_json) = 'object'),
  CONSTRAINT chk_pim_models_meta_object CHECK (jsonb_typeof(meta_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pim_models_category
  ON pim_models (organization_id, category_id, status);

CREATE TABLE IF NOT EXISTS pim_model_fields (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  model_id TEXT NOT NULL,
  field_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  field_type TEXT NOT NULL DEFAULT 'text',
  required BOOLEAN NOT NULL DEFAULT FALSE,
  position INTEGER NOT NULL DEFAULT 0,
  allowed_values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  marketplace_mapping_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  competitor_mapping_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  value_rules_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_evidence_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, model_id, field_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, model_id) REFERENCES pim_models(organization_id, id) ON DELETE CASCADE,
  FOREIGN KEY (organization_id, category_id) REFERENCES pim_categories(organization_id, id) ON DELETE RESTRICT,
  CONSTRAINT chk_pim_model_fields_allowed_values_array CHECK (jsonb_typeof(allowed_values_json) = 'array'),
  CONSTRAINT chk_pim_model_fields_marketplace_mapping_object CHECK (jsonb_typeof(marketplace_mapping_json) = 'object'),
  CONSTRAINT chk_pim_model_fields_competitor_mapping_object CHECK (jsonb_typeof(competitor_mapping_json) = 'object'),
  CONSTRAINT chk_pim_model_fields_value_rules_object CHECK (jsonb_typeof(value_rules_json) = 'object'),
  CONSTRAINT chk_pim_model_fields_source_evidence_array CHECK (jsonb_typeof(source_evidence_json) = 'array')
);

CREATE INDEX IF NOT EXISTS idx_pim_model_fields_category_position
  ON pim_model_fields (organization_id, category_id, position);

CREATE INDEX IF NOT EXISTS idx_pim_model_fields_code
  ON pim_model_fields (organization_id, code);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pim_model_fields_model_code_unique
  ON pim_model_fields (organization_id, model_id, lower(code))
  WHERE code <> '';

CREATE INDEX IF NOT EXISTS idx_pim_model_fields_mapping_gin
  ON pim_model_fields USING GIN (marketplace_mapping_json);

CREATE TABLE IF NOT EXISTS pim_channel_links (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  id TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  link_type TEXT NOT NULL,
  external_id TEXT NULL,
  external_url TEXT NULL,
  title TEXT NULL,
  status TEXT NOT NULL DEFAULT 'draft',
  confidence NUMERIC(5, 4) NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  moderation_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  CONSTRAINT chk_pim_channel_links_payload_object CHECK (jsonb_typeof(payload_json) = 'object'),
  CONSTRAINT chk_pim_channel_links_moderation_object CHECK (jsonb_typeof(moderation_json) = 'object'),
  CONSTRAINT chk_pim_channel_links_confidence_range CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX IF NOT EXISTS idx_pim_channel_links_entity
  ON pim_channel_links (organization_id, entity_type, entity_id, provider, link_type);

CREATE INDEX IF NOT EXISTS idx_pim_channel_links_status
  ON pim_channel_links (organization_id, provider, status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pim_channel_links_external_unique
  ON pim_channel_links (organization_id, provider, link_type, external_id)
  WHERE external_id IS NOT NULL AND external_id <> '';

CREATE TABLE IF NOT EXISTS pim_runs (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  id TEXT NOT NULL,
  run_type TEXT NOT NULL,
  provider TEXT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  scope_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  counters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NULL,
  finished_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  CONSTRAINT chk_pim_runs_scope_object CHECK (jsonb_typeof(scope_json) = 'object'),
  CONSTRAINT chk_pim_runs_counters_object CHECK (jsonb_typeof(counters_json) = 'object'),
  CONSTRAINT chk_pim_runs_result_object CHECK (jsonb_typeof(result_json) = 'object'),
  CONSTRAINT chk_pim_runs_error_object CHECK (jsonb_typeof(error_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pim_runs_type_status
  ON pim_runs (organization_id, run_type, status, created_at DESC);

CREATE TABLE IF NOT EXISTS pim_connector_accounts (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  provider TEXT NOT NULL,
  account_id TEXT NOT NULL,
  title TEXT NOT NULL,
  auth_mode TEXT NULL,
  credentials_ref TEXT NULL,
  credentials_meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  settings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, provider, account_id),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  CONSTRAINT chk_pim_connector_accounts_credentials_meta_object CHECK (jsonb_typeof(credentials_meta_json) = 'object'),
  CONSTRAINT chk_pim_connector_accounts_settings_object CHECK (jsonb_typeof(settings_json) = 'object'),
  CONSTRAINT chk_pim_connector_accounts_status_object CHECK (jsonb_typeof(status_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_pim_connector_accounts_provider_enabled
  ON pim_connector_accounts (organization_id, provider, enabled);

CREATE TABLE IF NOT EXISTS pim_external_snapshots (
  organization_id TEXT NOT NULL DEFAULT 'org_default',
  provider TEXT NOT NULL,
  snapshot_type TEXT NOT NULL,
  snapshot_key TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  source_hash TEXT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NULL,
  PRIMARY KEY (organization_id, provider, snapshot_type, snapshot_key),
  FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE,
  CONSTRAINT chk_pim_external_snapshots_payload_shape CHECK (jsonb_typeof(payload_json) IN ('object', 'array'))
);

CREATE INDEX IF NOT EXISTS idx_pim_external_snapshots_expiry
  ON pim_external_snapshots (organization_id, provider, snapshot_type, expires_at);

CREATE INDEX IF NOT EXISTS idx_pim_external_snapshots_hash
  ON pim_external_snapshots (organization_id, provider, source_hash)
  WHERE source_hash IS NOT NULL;
