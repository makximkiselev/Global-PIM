CREATE TABLE IF NOT EXISTS dashboard_stats_rel (
  summary_key TEXT PRIMARY KEY,
  categories_count INTEGER NOT NULL DEFAULT 0,
  products_count INTEGER NOT NULL DEFAULT 0,
  templates_count INTEGER NOT NULL DEFAULT 0,
  connectors_configured INTEGER NOT NULL DEFAULT 0,
  connectors_total INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
