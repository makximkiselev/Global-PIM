CREATE TABLE IF NOT EXISTS dictionaries_rel (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  code TEXT NOT NULL,
  attr_id TEXT NOT NULL,
  attr_type TEXT NOT NULL DEFAULT 'select',
  scope TEXT NOT NULL DEFAULT 'both',
  is_service BOOLEAN NOT NULL DEFAULT FALSE,
  is_required BOOLEAN NOT NULL DEFAULT FALSE,
  param_group TEXT NULL,
  template_layer TEXT NULL,
  created_at TEXT NULL,
  updated_at TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_code
  ON dictionaries_rel(code);

CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_attr_id
  ON dictionaries_rel(attr_id);

CREATE TABLE IF NOT EXISTS dictionary_values_rel (
  dict_id TEXT NOT NULL,
  value_key TEXT NOT NULL,
  value_text TEXT NOT NULL,
  value_count INTEGER NOT NULL DEFAULT 0,
  last_seen TEXT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (dict_id, value_key)
);

CREATE INDEX IF NOT EXISTS idx_dictionary_values_rel_dict_position
  ON dictionary_values_rel(dict_id, position, value_text);

CREATE TABLE IF NOT EXISTS dictionary_value_sources_rel (
  dict_id TEXT NOT NULL,
  value_key TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (dict_id, value_key, source_name)
);

CREATE TABLE IF NOT EXISTS dictionary_aliases_rel (
  dict_id TEXT NOT NULL,
  alias_key TEXT NOT NULL,
  canonical_value TEXT NOT NULL,
  PRIMARY KEY (dict_id, alias_key)
);

CREATE TABLE IF NOT EXISTS dictionary_provider_refs_rel (
  dict_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  provider_param_id TEXT NULL,
  provider_param_name TEXT NULL,
  kind TEXT NULL,
  is_required BOOLEAN NOT NULL DEFAULT FALSE,
  allowed_values TEXT[] NULL,
  PRIMARY KEY (dict_id, provider)
);

CREATE TABLE IF NOT EXISTS dictionary_export_maps_rel (
  dict_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  canonical_key TEXT NOT NULL,
  provider_value TEXT NOT NULL,
  PRIMARY KEY (dict_id, provider, canonical_key)
);
