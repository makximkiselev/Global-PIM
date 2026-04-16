CREATE TABLE IF NOT EXISTS attribute_mappings_rel (
  catalog_category_id TEXT NOT NULL,
  row_id TEXT NOT NULL,
  catalog_name TEXT NOT NULL,
  param_group TEXT NOT NULL DEFAULT '',
  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  yandex_param_id TEXT NULL,
  yandex_param_name TEXT NULL,
  yandex_kind TEXT NULL,
  yandex_values TEXT[] NULL,
  yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
  yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
  ozon_param_id TEXT NULL,
  ozon_param_name TEXT NULL,
  ozon_kind TEXT NULL,
  ozon_values TEXT[] NULL,
  ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
  ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (catalog_category_id, row_id)
);

CREATE INDEX IF NOT EXISTS idx_attribute_mappings_rel_category
  ON attribute_mappings_rel(catalog_category_id, catalog_name);
