CREATE TABLE IF NOT EXISTS products_rel (
  id TEXT PRIMARY KEY,
  category_id TEXT NOT NULL,
  product_type TEXT NOT NULL DEFAULT 'single',
  status TEXT NOT NULL DEFAULT 'draft',
  title TEXT NOT NULL,
  sku_pim TEXT NULL,
  sku_gt TEXT NULL,
  group_id TEXT NULL,
  selected_params TEXT[] NOT NULL DEFAULT '{}'::text[],
  feature_params TEXT[] NOT NULL DEFAULT '{}'::text[],
  exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  extra_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TEXT NULL,
  updated_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_rel_category
  ON products_rel(category_id, title);

CREATE INDEX IF NOT EXISTS idx_products_rel_sku_gt
  ON products_rel(sku_gt);

CREATE INDEX IF NOT EXISTS idx_products_rel_sku_pim
  ON products_rel(sku_pim);

CREATE INDEX IF NOT EXISTS idx_products_rel_group
  ON products_rel(group_id);
