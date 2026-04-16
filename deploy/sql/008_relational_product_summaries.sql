CREATE TABLE IF NOT EXISTS category_template_resolution_rel (
  category_id TEXT PRIMARY KEY,
  template_id TEXT NULL,
  template_name TEXT NULL,
  source_category_id TEXT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_marketplace_status_rel (
  product_id TEXT PRIMARY KEY,
  yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
  yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
  ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
  ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
