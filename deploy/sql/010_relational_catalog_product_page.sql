CREATE TABLE IF NOT EXISTS catalog_product_page_rel (
  product_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  category_id TEXT NOT NULL,
  category_path TEXT NOT NULL DEFAULT '',
  sku_pim TEXT NULL,
  sku_gt TEXT NULL,
  group_id TEXT NULL,
  group_name TEXT NULL,
  template_id TEXT NULL,
  template_name TEXT NULL,
  template_source_category_id TEXT NULL,
  yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
  yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
  ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
  ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
  preview_url TEXT NULL,
  exports_enabled_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_category
  ON catalog_product_page_rel(category_id, title);

CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_group
  ON catalog_product_page_rel(group_id);

CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_template
  ON catalog_product_page_rel(template_id);
