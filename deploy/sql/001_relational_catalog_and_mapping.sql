CREATE TABLE IF NOT EXISTS catalog_nodes_rel (
  id TEXT PRIMARY KEY,
  parent_id TEXT NULL,
  name TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  template_id TEXT NULL,
  products_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalog_nodes_rel_parent_position
  ON catalog_nodes_rel(parent_id, position);

CREATE TABLE IF NOT EXISTS category_mappings_rel (
  catalog_category_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_category_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (catalog_category_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_category_mappings_rel_provider
  ON category_mappings_rel(provider, provider_category_id);
