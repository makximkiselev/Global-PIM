CREATE TABLE IF NOT EXISTS catalog_product_registry_rel (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category_id TEXT NOT NULL,
  sku_pim TEXT NULL,
  sku_gt TEXT NULL,
  group_id TEXT NULL,
  preview_url TEXT NULL,
  exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_category
  ON catalog_product_registry_rel(category_id, title);

CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_sku_gt
  ON catalog_product_registry_rel(sku_gt);

CREATE TABLE IF NOT EXISTS category_product_counts_rel (
  category_id TEXT PRIMARY KEY,
  products_count INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
