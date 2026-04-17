CREATE TABLE IF NOT EXISTS product_variants_rel (
  id TEXT PRIMARY KEY,
  product_id TEXT NOT NULL,
  sku TEXT NULL,
  sku_pim TEXT NULL,
  sku_gt TEXT NULL,
  title TEXT NULL,
  links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_product_variants_rel_product
  ON product_variants_rel(product_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_product_variants_rel_sku
  ON product_variants_rel(sku)
  WHERE COALESCE(sku, '') <> '';
