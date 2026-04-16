CREATE TABLE IF NOT EXISTS templates_rel (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category_id TEXT NULL,
  created_at TEXT NULL,
  updated_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_templates_rel_category
  ON templates_rel(category_id);

CREATE TABLE IF NOT EXISTS template_attributes_rel (
  template_id TEXT NOT NULL,
  attr_id TEXT NOT NULL,
  name TEXT NOT NULL,
  code TEXT NOT NULL,
  attr_type TEXT NOT NULL,
  is_required BOOLEAN NOT NULL DEFAULT FALSE,
  scope TEXT NOT NULL DEFAULT 'common',
  attribute_id TEXT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  is_locked BOOLEAN NOT NULL DEFAULT FALSE,
  options_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (template_id, attr_id)
);

CREATE INDEX IF NOT EXISTS idx_template_attributes_rel_template_position
  ON template_attributes_rel(template_id, position, code);

CREATE TABLE IF NOT EXISTS category_template_links_rel (
  category_id TEXT NOT NULL,
  template_id TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (category_id, template_id)
);

CREATE INDEX IF NOT EXISTS idx_category_template_links_rel_category_position
  ON category_template_links_rel(category_id, position);
