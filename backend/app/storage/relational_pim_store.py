from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.control_plane import DEFAULT_ORGANIZATION_ID
from app.core.tenant_context import current_tenant_organization_id
from app.core.json_store import (
    DATA_DIR,
    _is_retryable_pg_error,
    _pg_connect,
    _reset_pg_connection,
    read_doc,
    with_lock,
    write_doc,
)

CATALOG_NODES_PATH = DATA_DIR / "catalog_nodes.json"
CATEGORY_MAPPINGS_PATH = DATA_DIR / "marketplaces" / "category_mapping.json"
ATTRIBUTE_MAPPINGS_PATH = DATA_DIR / "marketplaces" / "attribute_master_mapping.json"
ATTRIBUTE_VALUE_DICTIONARY_PATH = DATA_DIR / "marketplaces" / "attribute_value_dictionary.json"
DICTIONARIES_PATH = DATA_DIR / "dictionaries.json"
DICTS_DIR = DATA_DIR / "dicts"
TEMPLATES_PATH = DATA_DIR / "templates.json"
PRODUCTS_PATH = DATA_DIR / "products.json"
VARIANTS_PATH = DATA_DIR / "product_variants.json"
PRODUCT_GROUPS_PATH = DATA_DIR / "product_groups.json"
CONNECTORS_STATE_PATH = DATA_DIR / "marketplaces" / "connectors_scheduler.json"
_TABLES_READY = False
_TABLES_READY_LOCK = threading.Lock()
_CATALOG_NODES_READY = False
_CATALOG_NODES_READY_LOCK = threading.Lock()
_TEMPLATES_TENANT_READY: set[str] = set()
_TEMPLATES_TENANT_READY_LOCK = threading.Lock()


def _with_pg_retry(fn):
    try:
        return fn()
    except Exception as exc:
        if not _is_retryable_pg_error(exc):
            raise
        _reset_pg_connection()
        return fn()


def _normalize_organization_id(value: Optional[str]) -> str:
    org_id = str(value or "").strip()
    return org_id or DEFAULT_ORGANIZATION_ID


def _resolve_organization_id(value: Optional[str]) -> str:
    if value is None:
        return _normalize_organization_id(current_tenant_organization_id())
    return _normalize_organization_id(value)


def _ensure_tables_impl() -> None:
    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_nodes_rel (
                  id TEXT PRIMARY KEY,
                  parent_id TEXT NULL,
                  name TEXT NOT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  template_id TEXT NULL,
                  products_count INTEGER NOT NULL DEFAULT 0,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_nodes_rel_parent_position
                  ON catalog_nodes_rel(parent_id, position)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_mappings_rel (
                  catalog_category_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  provider_category_id TEXT NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (catalog_category_id, provider)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_mappings_tenant_rel (
                  organization_id TEXT NOT NULL,
                  catalog_category_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  provider_category_id TEXT NOT NULL,
                  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, catalog_category_id, provider)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category_mappings_rel_provider
                  ON category_mappings_rel(provider, provider_category_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category_mappings_tenant_rel_provider
                  ON category_mappings_tenant_rel(organization_id, provider, provider_category_id)
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attribute_mappings_tenant_rel (
                  organization_id TEXT NOT NULL,
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
                  PRIMARY KEY (organization_id, catalog_category_id, row_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_attribute_mappings_rel_category
                  ON attribute_mappings_rel(catalog_category_id, catalog_name)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_attribute_mappings_tenant_rel_category
                  ON attribute_mappings_tenant_rel(organization_id, catalog_category_id, catalog_name)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attribute_value_refs_rel (
                  catalog_category_id TEXT NOT NULL,
                  catalog_name_key TEXT NOT NULL,
                  catalog_name TEXT NOT NULL,
                  param_group TEXT NOT NULL DEFAULT '',
                  attribute_id TEXT NULL,
                  dict_id TEXT NULL,
                  value_type TEXT NULL,
                  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_provider_category_id TEXT NULL,
                  yandex_param_id TEXT NULL,
                  yandex_param_name TEXT NULL,
                  yandex_kind TEXT NULL,
                  yandex_allowed_values TEXT[] NULL,
                  yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_provider_category_id TEXT NULL,
                  ozon_param_id TEXT NULL,
                  ozon_param_name TEXT NULL,
                  ozon_kind TEXT NULL,
                  ozon_allowed_values TEXT[] NULL,
                  ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
                  rows_count INTEGER NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (catalog_category_id, catalog_name_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS attribute_value_refs_tenant_rel (
                  organization_id TEXT NOT NULL,
                  catalog_category_id TEXT NOT NULL,
                  catalog_name_key TEXT NOT NULL,
                  catalog_name TEXT NOT NULL,
                  param_group TEXT NOT NULL DEFAULT '',
                  attribute_id TEXT NULL,
                  dict_id TEXT NULL,
                  value_type TEXT NULL,
                  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_provider_category_id TEXT NULL,
                  yandex_param_id TEXT NULL,
                  yandex_param_name TEXT NULL,
                  yandex_kind TEXT NULL,
                  yandex_allowed_values TEXT[] NULL,
                  yandex_required BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_export BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_provider_category_id TEXT NULL,
                  ozon_param_id TEXT NULL,
                  ozon_param_name TEXT NULL,
                  ozon_kind TEXT NULL,
                  ozon_allowed_values TEXT[] NULL,
                  ozon_required BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_export BOOLEAN NOT NULL DEFAULT FALSE,
                  rows_count INTEGER NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, catalog_category_id, catalog_name_key)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_attribute_value_refs_rel_category
                  ON attribute_value_refs_rel(catalog_category_id, catalog_name)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_attribute_value_refs_tenant_rel_category
                  ON attribute_value_refs_tenant_rel(organization_id, catalog_category_id, catalog_name)
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionaries_tenant_rel (
                  organization_id TEXT NOT NULL,
                  id TEXT NOT NULL,
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
                  updated_at TEXT NULL,
                  PRIMARY KEY (organization_id, id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_code
                  ON dictionaries_rel(code)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionaries_tenant_rel_code
                  ON dictionaries_tenant_rel(organization_id, code)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_attr_id
                  ON dictionaries_rel(attr_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionaries_tenant_rel_attr_id
                  ON dictionaries_tenant_rel(organization_id, attr_id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_values_rel (
                  dict_id TEXT NOT NULL,
                  value_key TEXT NOT NULL,
                  value_text TEXT NOT NULL,
                  value_count INTEGER NOT NULL DEFAULT 0,
                  last_seen TEXT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (dict_id, value_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_values_tenant_rel (
                  organization_id TEXT NOT NULL,
                  dict_id TEXT NOT NULL,
                  value_key TEXT NOT NULL,
                  value_text TEXT NOT NULL,
                  value_count INTEGER NOT NULL DEFAULT 0,
                  last_seen TEXT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (organization_id, dict_id, value_key)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionary_values_rel_dict_position
                  ON dictionary_values_rel(dict_id, position, value_text)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dictionary_values_tenant_rel_dict_position
                  ON dictionary_values_tenant_rel(organization_id, dict_id, position, value_text)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_value_sources_rel (
                  dict_id TEXT NOT NULL,
                  value_key TEXT NOT NULL,
                  source_name TEXT NOT NULL,
                  source_count INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (dict_id, value_key, source_name)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_value_sources_tenant_rel (
                  organization_id TEXT NOT NULL,
                  dict_id TEXT NOT NULL,
                  value_key TEXT NOT NULL,
                  source_name TEXT NOT NULL,
                  source_count INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (organization_id, dict_id, value_key, source_name)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_aliases_rel (
                  dict_id TEXT NOT NULL,
                  alias_key TEXT NOT NULL,
                  canonical_value TEXT NOT NULL,
                  PRIMARY KEY (dict_id, alias_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_aliases_tenant_rel (
                  organization_id TEXT NOT NULL,
                  dict_id TEXT NOT NULL,
                  alias_key TEXT NOT NULL,
                  canonical_value TEXT NOT NULL,
                  PRIMARY KEY (organization_id, dict_id, alias_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_provider_refs_rel (
                  dict_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  provider_param_id TEXT NULL,
                  provider_param_name TEXT NULL,
                  kind TEXT NULL,
                  is_required BOOLEAN NOT NULL DEFAULT FALSE,
                  allowed_values TEXT[] NULL,
                  PRIMARY KEY (dict_id, provider)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_provider_refs_tenant_rel (
                  organization_id TEXT NOT NULL,
                  dict_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  provider_param_id TEXT NULL,
                  provider_param_name TEXT NULL,
                  kind TEXT NULL,
                  is_required BOOLEAN NOT NULL DEFAULT FALSE,
                  allowed_values TEXT[] NULL,
                  PRIMARY KEY (organization_id, dict_id, provider)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_export_maps_rel (
                  dict_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  canonical_key TEXT NOT NULL,
                  provider_value TEXT NOT NULL,
                  PRIMARY KEY (dict_id, provider, canonical_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dictionary_export_maps_tenant_rel (
                  organization_id TEXT NOT NULL,
                  dict_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  canonical_key TEXT NOT NULL,
                  provider_value TEXT NOT NULL,
                  PRIMARY KEY (organization_id, dict_id, provider, canonical_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS templates_rel (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  category_id TEXT NULL,
                  created_at TEXT NULL,
                  updated_at TEXT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS templates_tenant_rel (
                  organization_id TEXT NOT NULL,
                  id TEXT NOT NULL,
                  name TEXT NOT NULL,
                  category_id TEXT NULL,
                  created_at TEXT NULL,
                  updated_at TEXT NULL,
                  PRIMARY KEY (organization_id, id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_templates_rel_category
                  ON templates_rel(category_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_templates_tenant_rel_category
                  ON templates_tenant_rel(organization_id, category_id)
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS template_attributes_tenant_rel (
                  organization_id TEXT NOT NULL,
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
                  PRIMARY KEY (organization_id, template_id, attr_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_template_attributes_rel_template_position
                  ON template_attributes_rel(template_id, position, code)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_template_attributes_tenant_rel_template_position
                  ON template_attributes_tenant_rel(organization_id, template_id, position, code)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_template_links_rel (
                  category_id TEXT NOT NULL,
                  template_id TEXT NOT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (category_id, template_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_template_links_tenant_rel (
                  organization_id TEXT NOT NULL,
                  category_id TEXT NOT NULL,
                  template_id TEXT NOT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (organization_id, category_id, template_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category_template_links_rel_category_position
                  ON category_template_links_rel(category_id, position)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category_template_links_tenant_rel_category_position
                  ON category_template_links_tenant_rel(organization_id, category_id, position)
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_products_rel_category
                  ON products_rel(category_id, title)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_products_rel_sku_gt
                  ON products_rel(sku_gt)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_products_rel_sku_pim
                  ON products_rel(sku_pim)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_products_rel_group
                  ON products_rel(group_id)
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_category
                  ON catalog_product_registry_rel(category_id, title)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_registry_rel_sku_gt
                  ON catalog_product_registry_rel(sku_gt)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_product_counts_rel (
                  category_id TEXT PRIMARY KEY,
                  products_count INTEGER NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_template_resolution_rel (
                  category_id TEXT PRIMARY KEY,
                  template_id TEXT NULL,
                  template_name TEXT NULL,
                  source_category_id TEXT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS category_template_resolution_tenant_rel (
                  organization_id TEXT NOT NULL,
                  category_id TEXT NOT NULL,
                  template_id TEXT NULL,
                  template_name TEXT NULL,
                  source_category_id TEXT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, category_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_category_template_resolution_tenant_rel_category
                  ON category_template_resolution_tenant_rel(organization_id, category_id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_marketplace_status_rel (
                  product_id TEXT PRIMARY KEY,
                  yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
                  ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_marketplace_status_tenant_rel (
                  organization_id TEXT NOT NULL,
                  product_id TEXT NOT NULL,
                  yandex_present BOOLEAN NOT NULL DEFAULT FALSE,
                  yandex_status TEXT NOT NULL DEFAULT 'Нет данных',
                  ozon_present BOOLEAN NOT NULL DEFAULT FALSE,
                  ozon_status TEXT NOT NULL DEFAULT 'Нет данных',
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, product_id)
                )
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_product_page_tenant_rel (
                  organization_id TEXT NOT NULL,
                  product_id TEXT NOT NULL,
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
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, product_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_category
                  ON catalog_product_page_rel(category_id, title)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_group
                  ON catalog_product_page_rel(group_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_rel_template
                  ON catalog_product_page_rel(template_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_product_marketplace_status_tenant_rel_org
                  ON product_marketplace_status_tenant_rel(organization_id, product_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_category
                  ON catalog_product_page_tenant_rel(organization_id, category_id, title)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_group
                  ON catalog_product_page_tenant_rel(organization_id, group_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_catalog_product_page_tenant_rel_template
                  ON catalog_product_page_tenant_rel(organization_id, template_id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS dashboard_stats_rel (
                  summary_key TEXT PRIMARY KEY,
                  categories_count INTEGER NOT NULL DEFAULT 0,
                  products_count INTEGER NOT NULL DEFAULT 0,
                  templates_count INTEGER NOT NULL DEFAULT 0,
                  connectors_configured INTEGER NOT NULL DEFAULT 0,
                  connectors_total INTEGER NOT NULL DEFAULT 0,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_groups_rel (
                  id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  created_at TEXT NULL,
                  updated_at TEXT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS product_group_variant_params_rel (
                  group_id TEXT NOT NULL,
                  param_id TEXT NOT NULL,
                  position INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY (group_id, param_id)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_product_group_variant_params_rel_group
                  ON product_group_variant_params_rel(group_id, position)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_method_state_rel (
                  provider TEXT NOT NULL,
                  method TEXT NOT NULL,
                  schedule TEXT NOT NULL,
                  last_run_at TEXT NULL,
                  last_success_at TEXT NULL,
                  last_error_at TEXT NULL,
                  last_error TEXT NOT NULL DEFAULT '',
                  fail_count INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'ok',
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (provider, method)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_method_state_tenant_rel (
                  organization_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  method TEXT NOT NULL,
                  schedule TEXT NOT NULL,
                  last_run_at TEXT NULL,
                  last_success_at TEXT NULL,
                  last_error_at TEXT NULL,
                  last_error TEXT NOT NULL DEFAULT '',
                  fail_count INTEGER NOT NULL DEFAULT 0,
                  status TEXT NOT NULL DEFAULT 'ok',
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, provider, method)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_provider_settings_rel (
                  provider TEXT NOT NULL,
                  setting_key TEXT NOT NULL,
                  setting_value TEXT NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (provider, setting_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_provider_settings_tenant_rel (
                  organization_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  setting_key TEXT NOT NULL,
                  setting_value TEXT NOT NULL,
                  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                  PRIMARY KEY (organization_id, provider, setting_key)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_import_stores_rel (
                  provider TEXT NOT NULL,
                  store_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  business_id TEXT NULL,
                  client_id TEXT NULL,
                  api_key TEXT NULL,
                  token TEXT NULL,
                  auth_mode TEXT NULL,
                  enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  notes TEXT NULL,
                  last_check_at TEXT NULL,
                  last_check_status TEXT NULL,
                  last_check_error TEXT NULL,
                  created_at TEXT NULL,
                  updated_at TEXT NULL,
                  PRIMARY KEY (provider, store_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS connector_import_stores_tenant_rel (
                  organization_id TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  store_id TEXT NOT NULL,
                  title TEXT NOT NULL,
                  business_id TEXT NULL,
                  client_id TEXT NULL,
                  api_key TEXT NULL,
                  token TEXT NULL,
                  auth_mode TEXT NULL,
                  enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  notes TEXT NULL,
                  last_check_at TEXT NULL,
                  last_check_status TEXT NULL,
                  last_check_error TEXT NULL,
                  created_at TEXT NULL,
                  updated_at TEXT NULL,
                  PRIMARY KEY (organization_id, provider, store_id)
                )
                """
            )
            cur.execute(
                """
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
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_product_variants_rel_product
                  ON product_variants_rel(product_id)
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_product_variants_rel_sku
                  ON product_variants_rel(sku)
                  WHERE COALESCE(sku, '') <> ''
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_connector_import_stores_rel_provider
                  ON connector_import_stores_rel(provider, enabled)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_connector_import_stores_tenant_rel_provider
                  ON connector_import_stores_tenant_rel(organization_id, provider, enabled)
                """
            )

    _with_pg_retry(_run)


def _schema_bootstrap_marker_exists() -> bool:
    def _run() -> bool:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.connector_import_stores_tenant_rel')")
            row = cur.fetchone()
        return bool(row and row[0])

    return bool(_with_pg_retry(_run))


def _ensure_tables() -> None:
    global _TABLES_READY
    if _TABLES_READY:
        return
    with _TABLES_READY_LOCK:
        if _TABLES_READY:
            return
        if _schema_bootstrap_marker_exists():
            _TABLES_READY = True
            return
        _ensure_tables_impl()
        _TABLES_READY = True


def _table_count(table_name: str) -> int:
    def _run() -> int:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row = cur.fetchone()
        return int((row or [0])[0] or 0)

    return int(_with_pg_retry(_run) or 0)


def _replace_catalog_nodes_table(nodes: List[Dict[str, Any]]) -> None:
    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_nodes_rel")
            if nodes:
                cur.executemany(
                    """
                    INSERT INTO catalog_nodes_rel (
                      id, parent_id, name, position, template_id, products_count, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    [
                        (
                            str(node.get("id") or "").strip(),
                            str(node.get("parent_id") or "").strip() or None,
                            str(node.get("name") or "").strip(),
                            int(node.get("position") or 0),
                            str(node.get("template_id") or "").strip() or None,
                            int(node.get("products_count") or 0),
                        )
                        for node in nodes
                        if str(node.get("id") or "").strip()
                    ],
                )

    _with_pg_retry(_run)


def _replace_category_mappings_table(items: Dict[str, Dict[str, str]]) -> None:
    rows: List[tuple[str, str, str]] = []
    for catalog_category_id, mapping in (items or {}).items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(mapping, dict):
            continue
        for provider, provider_category_id in mapping.items():
            p = str(provider or "").strip()
            pcid = str(provider_category_id or "").strip()
            if cid and p and pcid:
                rows.append((cid, p, pcid))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_mappings_rel")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO category_mappings_rel (
                      catalog_category_id, provider, provider_category_id, updated_at
                    ) VALUES (%s, %s, %s, NOW())
                    """,
                    rows,
                )

    _with_pg_retry(_run)


def _replace_category_mappings_tenant_table(items: Dict[str, Dict[str, str]], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    rows: List[tuple[str, str, str, str]] = []
    for catalog_category_id, mapping in (items or {}).items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(mapping, dict):
            continue
        for provider, provider_category_id in mapping.items():
            p = str(provider or "").strip()
            pcid = str(provider_category_id or "").strip()
            if cid and p and pcid:
                rows.append((org_id, cid, p, pcid))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_mappings_tenant_rel WHERE organization_id = %s", [org_id])
            if rows:
                cur.executemany(
                    """
                    INSERT INTO category_mappings_tenant_rel (
                      organization_id, catalog_category_id, provider, provider_category_id, updated_at
                    ) VALUES (%s, %s, %s, %s, NOW())
                    """,
                    rows,
                )

    _with_pg_retry(_run)


def _bootstrap_catalog_nodes_from_legacy() -> None:
    global _CATALOG_NODES_READY
    if _CATALOG_NODES_READY:
        return
    lock = with_lock("catalog_nodes_rel_bootstrap")
    lock.acquire()
    try:
        if _CATALOG_NODES_READY:
            return
        if _table_count("catalog_nodes_rel") > 0:
            _CATALOG_NODES_READY = True
            return
        doc = read_doc(CATALOG_NODES_PATH, default=[])
        nodes = doc if isinstance(doc, list) else []
        _replace_catalog_nodes_table(nodes)
        _CATALOG_NODES_READY = True
    finally:
        lock.release()


def _bootstrap_category_mappings_from_legacy() -> None:
    lock = with_lock("category_mappings_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("category_mappings_rel") > 0:
            return
        doc = read_doc(CATEGORY_MAPPINGS_PATH, default={"version": 1, "items": {}})
        items = doc.get("items") if isinstance(doc, dict) else {}
        if not isinstance(items, dict):
            items = {}
        _replace_category_mappings_table(items)
    finally:
        lock.release()


def _bootstrap_category_mappings_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"category_mappings_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM category_mappings_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_category_mappings_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            legacy_doc = read_doc(CATEGORY_MAPPINGS_PATH, default={"version": 1, "items": {}})
            items = legacy_doc.get("items") if isinstance(legacy_doc, dict) else {}
            if not isinstance(items, dict):
                items = {}
            _replace_category_mappings_tenant_table(items, org_id)
    finally:
        lock.release()


def _replace_attribute_mappings_table(doc: Dict[str, Any]) -> None:
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    rows: List[tuple[Any, ...]] = []
    for catalog_category_id, payload in items.items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(payload, dict):
            continue
        for row in payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            provider_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            yandex = provider_map.get("yandex_market") if isinstance(provider_map.get("yandex_market"), dict) else {}
            ozon = provider_map.get("ozon") if isinstance(provider_map.get("ozon"), dict) else {}
            rows.append(
                (
                    cid,
                    str(row.get("id") or "").strip(),
                    str(row.get("catalog_name") or "").strip(),
                    str(row.get("group") or "").strip(),
                    bool(row.get("confirmed") or False),
                    str(yandex.get("id") or "").strip() or None,
                    str(yandex.get("name") or "").strip() or None,
                    str(yandex.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (yandex.get("values") or []) if str(v).strip()] or None,
                    bool(yandex.get("required") or False),
                    bool(yandex.get("export") or False),
                    str(ozon.get("id") or "").strip() or None,
                    str(ozon.get("name") or "").strip() or None,
                    str(ozon.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (ozon.get("values") or []) if str(v).strip()] or None,
                    bool(ozon.get("required") or False),
                    bool(ozon.get("export") or False),
                )
            )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attribute_mappings_rel")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO attribute_mappings_rel (
                      catalog_category_id, row_id, catalog_name, param_group, confirmed,
                      yandex_param_id, yandex_param_name, yandex_kind, yandex_values, yandex_required, yandex_export,
                      ozon_param_id, ozon_param_name, ozon_kind, ozon_values, ozon_required, ozon_export,
                      updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      NOW()
                    )
                    """,
                    rows,
                )

    _with_pg_retry(_run)


def _collect_attribute_mapping_rows(doc: Dict[str, Any]) -> List[tuple[Any, ...]]:
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    rows: List[tuple[Any, ...]] = []
    for catalog_category_id, payload in items.items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(payload, dict):
            continue
        for row in payload.get("rows") or []:
            if not isinstance(row, dict):
                continue
            provider_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            yandex = provider_map.get("yandex_market") if isinstance(provider_map.get("yandex_market"), dict) else {}
            ozon = provider_map.get("ozon") if isinstance(provider_map.get("ozon"), dict) else {}
            rows.append(
                (
                    cid,
                    str(row.get("id") or "").strip(),
                    str(row.get("catalog_name") or "").strip(),
                    str(row.get("group") or "").strip(),
                    bool(row.get("confirmed") or False),
                    str(yandex.get("id") or "").strip() or None,
                    str(yandex.get("name") or "").strip() or None,
                    str(yandex.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (yandex.get("values") or []) if str(v).strip()] or None,
                    bool(yandex.get("required") or False),
                    bool(yandex.get("export") or False),
                    str(ozon.get("id") or "").strip() or None,
                    str(ozon.get("name") or "").strip() or None,
                    str(ozon.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (ozon.get("values") or []) if str(v).strip()] or None,
                    bool(ozon.get("required") or False),
                    bool(ozon.get("export") or False),
                )
            )
    return rows


def _replace_attribute_mappings_tenant_table(doc: Dict[str, Any], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    rows = _collect_attribute_mapping_rows(doc)

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attribute_mappings_tenant_rel WHERE organization_id = %s", [org_id])
            if rows:
                cur.executemany(
                    """
                    INSERT INTO attribute_mappings_tenant_rel (
                      organization_id, catalog_category_id, row_id, catalog_name, param_group, confirmed,
                      yandex_param_id, yandex_param_name, yandex_kind, yandex_values, yandex_required, yandex_export,
                      ozon_param_id, ozon_param_name, ozon_kind, ozon_values, ozon_required, ozon_export,
                      updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s,
                      NOW()
                    )
                    """,
                    [(org_id, *row) for row in rows],
                )

    _with_pg_retry(_run)


def _bootstrap_attribute_mappings_from_legacy() -> None:
    lock = with_lock("attribute_mappings_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("attribute_mappings_rel") > 0:
            return
        doc = read_doc(ATTRIBUTE_MAPPINGS_PATH, default={"version": 1, "items": {}})
        if not isinstance(doc, dict):
            doc = {"version": 1, "items": {}}
        _replace_attribute_mappings_table(doc)
    finally:
        lock.release()


def _bootstrap_attribute_mappings_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"attribute_mappings_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM attribute_mappings_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_attribute_mappings_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            doc = read_doc(ATTRIBUTE_MAPPINGS_PATH, default={"version": 1, "items": {}})
            if not isinstance(doc, dict):
                doc = {"version": 1, "items": {}}
            _replace_attribute_mappings_tenant_table(doc, org_id)
    finally:
        lock.release()


def _replace_attribute_value_refs_table(doc: Dict[str, Any]) -> None:
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    rows: List[tuple[Any, ...]] = []
    for catalog_category_id, payload in items.items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(payload, dict):
            continue
        providers_payload = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
        yandex_provider = providers_payload.get("yandex_market") if isinstance(providers_payload.get("yandex_market"), dict) else {}
        ozon_provider = providers_payload.get("ozon") if isinstance(providers_payload.get("ozon"), dict) else {}
        catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
        for key, raw in catalog_params.items():
            if not isinstance(raw, dict):
                continue
            yandex_binding = (raw.get("bindings") or {}).get("yandex_market") if isinstance(raw.get("bindings"), dict) and isinstance((raw.get("bindings") or {}).get("yandex_market"), dict) else {}
            ozon_binding = (raw.get("bindings") or {}).get("ozon") if isinstance(raw.get("bindings"), dict) and isinstance((raw.get("bindings") or {}).get("ozon"), dict) else {}
            rows.append(
                (
                    cid,
                    str(key or "").strip(),
                    str(raw.get("catalog_name") or "").strip(),
                    str(raw.get("group") or "").strip(),
                    str(raw.get("attribute_id") or "").strip() or None,
                    str(raw.get("dict_id") or "").strip() or None,
                    str(raw.get("type") or "").strip() or None,
                    bool(raw.get("confirmed") or False),
                    str(yandex_provider.get("provider_category_id") or "").strip() or None,
                    str(yandex_binding.get("id") or "").strip() or None,
                    str(yandex_binding.get("name") or "").strip() or None,
                    str(yandex_binding.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (yandex_binding.get("values") or []) if str(v).strip()] or None,
                    bool(yandex_binding.get("required") or False),
                    bool(yandex_binding.get("export") or False),
                    str(ozon_provider.get("provider_category_id") or "").strip() or None,
                    str(ozon_binding.get("id") or "").strip() or None,
                    str(ozon_binding.get("name") or "").strip() or None,
                    str(ozon_binding.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (ozon_binding.get("values") or []) if str(v).strip()] or None,
                    bool(ozon_binding.get("required") or False),
                    bool(ozon_binding.get("export") or False),
                    int(payload.get("rows_count") or 0),
                )
            )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attribute_value_refs_rel")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO attribute_value_refs_rel (
                      catalog_category_id, catalog_name_key, catalog_name, param_group, attribute_id, dict_id, value_type, confirmed,
                      yandex_provider_category_id, yandex_param_id, yandex_param_name, yandex_kind, yandex_allowed_values, yandex_required, yandex_export,
                      ozon_provider_category_id, ozon_param_id, ozon_param_name, ozon_kind, ozon_allowed_values, ozon_required, ozon_export,
                      rows_count, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, NOW()
                    )
                    """,
                    rows,
                )

    _with_pg_retry(_run)


def _collect_attribute_value_ref_rows(doc: Dict[str, Any]) -> List[tuple[Any, ...]]:
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    rows: List[tuple[Any, ...]] = []
    for catalog_category_id, payload in items.items():
        cid = str(catalog_category_id or "").strip()
        if not cid or not isinstance(payload, dict):
            continue
        providers_payload = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
        yandex_provider = providers_payload.get("yandex_market") if isinstance(providers_payload.get("yandex_market"), dict) else {}
        ozon_provider = providers_payload.get("ozon") if isinstance(providers_payload.get("ozon"), dict) else {}
        catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
        for key, raw in catalog_params.items():
            if not isinstance(raw, dict):
                continue
            yandex_binding = (raw.get("bindings") or {}).get("yandex_market") if isinstance(raw.get("bindings"), dict) and isinstance((raw.get("bindings") or {}).get("yandex_market"), dict) else {}
            ozon_binding = (raw.get("bindings") or {}).get("ozon") if isinstance(raw.get("bindings"), dict) and isinstance((raw.get("bindings") or {}).get("ozon"), dict) else {}
            rows.append(
                (
                    cid,
                    str(key or "").strip(),
                    str(raw.get("catalog_name") or "").strip(),
                    str(raw.get("group") or "").strip(),
                    str(raw.get("attribute_id") or "").strip() or None,
                    str(raw.get("dict_id") or "").strip() or None,
                    str(raw.get("type") or "").strip() or None,
                    bool(raw.get("confirmed") or False),
                    str(yandex_provider.get("provider_category_id") or "").strip() or None,
                    str(yandex_binding.get("id") or "").strip() or None,
                    str(yandex_binding.get("name") or "").strip() or None,
                    str(yandex_binding.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (yandex_binding.get("values") or []) if str(v).strip()] or None,
                    bool(yandex_binding.get("required") or False),
                    bool(yandex_binding.get("export") or False),
                    str(ozon_provider.get("provider_category_id") or "").strip() or None,
                    str(ozon_binding.get("id") or "").strip() or None,
                    str(ozon_binding.get("name") or "").strip() or None,
                    str(ozon_binding.get("kind") or "").strip() or None,
                    [str(v).strip() for v in (ozon_binding.get("values") or []) if str(v).strip()] or None,
                    bool(ozon_binding.get("required") or False),
                    bool(ozon_binding.get("export") or False),
                    int(payload.get("rows_count") or 0),
                )
            )
    return rows


def _attribute_value_ref_dedupe_key(row: tuple[Any, ...]) -> tuple[str, str]:
    category_id = str(row[0] or "").strip()
    catalog_name_key = str(row[1] or "").strip()
    catalog_name = str(row[2] or "").strip()
    normalized_name = " ".join((catalog_name or catalog_name_key).lower().split())
    return category_id, normalized_name


def _replace_attribute_value_refs_tenant_table(doc: Dict[str, Any], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    deduped_rows: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in _collect_attribute_value_ref_rows(doc):
        category_id, normalized_name = _attribute_value_ref_dedupe_key(row)
        if not category_id or not normalized_name:
            continue
        deduped_rows[(category_id, normalized_name)] = row
    rows = list(deduped_rows.values())

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM attribute_value_refs_tenant_rel WHERE organization_id = %s", [org_id])
            if rows:
                cur.executemany(
                    """
                    INSERT INTO attribute_value_refs_tenant_rel (
                      organization_id, catalog_category_id, catalog_name_key, catalog_name, param_group, attribute_id, dict_id, value_type, confirmed,
                      yandex_provider_category_id, yandex_param_id, yandex_param_name, yandex_kind, yandex_allowed_values, yandex_required, yandex_export,
                      ozon_provider_category_id, ozon_param_id, ozon_param_name, ozon_kind, ozon_allowed_values, ozon_required, ozon_export,
                      rows_count, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, NOW()
                    )
                    """,
                    [(org_id, *row) for row in rows],
                )

    _with_pg_retry(_run)


def save_attribute_value_refs_category_doc(
    catalog_category_id: str,
    payload: Dict[str, Any],
    organization_id: Optional[str] = None,
) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    cid = str(catalog_category_id or "").strip()
    if not cid:
        return
    doc = {
        "version": 2,
        "updated_at": None,
        "items": {
            cid: payload if isinstance(payload, dict) else {},
        },
    }
    deduped_rows: dict[tuple[str, str], tuple[Any, ...]] = {}
    for row in _collect_attribute_value_ref_rows(doc):
        category_id, normalized_name = _attribute_value_ref_dedupe_key(row)
        if not category_id or not normalized_name:
            continue
        deduped_rows[(category_id, normalized_name)] = row
    rows = [row for row in deduped_rows.values() if str(row[0] or "").strip() == cid]

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM attribute_value_refs_tenant_rel
                WHERE organization_id = %s AND catalog_category_id = %s
                """,
                [org_id, cid],
            )
            if rows:
                cur.executemany(
                    """
                    INSERT INTO attribute_value_refs_tenant_rel (
                      organization_id, catalog_category_id, catalog_name_key, catalog_name, param_group, attribute_id, dict_id, value_type, confirmed,
                      yandex_provider_category_id, yandex_param_id, yandex_param_name, yandex_kind, yandex_allowed_values, yandex_required, yandex_export,
                      ozon_provider_category_id, ozon_param_id, ozon_param_name, ozon_kind, ozon_allowed_values, ozon_required, ozon_export,
                      rows_count, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, NOW()
                    )
                    """,
                    [(org_id, *row) for row in rows],
                )

    _with_pg_retry(_run)


def _bootstrap_attribute_value_refs_from_legacy() -> None:
    lock = with_lock("attribute_value_refs_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("attribute_value_refs_rel") > 0:
            return
        doc = read_doc(ATTRIBUTE_VALUE_DICTIONARY_PATH, default={"version": 2, "updated_at": None, "items": {}})
        if not isinstance(doc, dict):
            doc = {"version": 2, "updated_at": None, "items": {}}
        _replace_attribute_value_refs_table(doc)
    finally:
        lock.release()


def _bootstrap_attribute_value_refs_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"attribute_value_refs_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM attribute_value_refs_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_attribute_value_refs_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            doc = read_doc(ATTRIBUTE_VALUE_DICTIONARY_PATH, default={"version": 2, "updated_at": None, "items": {}})
            if not isinstance(doc, dict):
                doc = {"version": 2, "updated_at": None, "items": {}}
            _replace_attribute_value_refs_tenant_table(doc, org_id)
    finally:
        lock.release()


def _replace_product_marketplace_status_tenant_table(rows: List[Dict[str, Any]], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    payload: List[tuple[str, str, bool, str, bool, str]] = []
    for row in rows or []:
        pid = str(row.get("product_id") or "").strip()
        if not pid:
            continue
        payload.append(
            (
                org_id,
                pid,
                bool(row.get("yandex_present") or False),
                str(row.get("yandex_status") or "Нет данных").strip() or "Нет данных",
                bool(row.get("ozon_present") or False),
                str(row.get("ozon_status") or "Нет данных").strip() or "Нет данных",
            )
        )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_marketplace_status_tenant_rel WHERE organization_id = %s", [org_id])
            if payload:
                cur.executemany(
                    """
                    INSERT INTO product_marketplace_status_tenant_rel (
                      organization_id, product_id, yandex_present, yandex_status, ozon_present, ozon_status, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    payload,
                )

    _with_pg_retry(_run)


def _bootstrap_product_marketplace_status_from_legacy() -> None:
    _ensure_tables()
    lock = with_lock("product_marketplace_status_rel_bootstrap")
    lock.acquire()
    try:
        # Legacy source is the relational table itself. If it's empty there is nothing to bootstrap.
        return
    finally:
        lock.release()


def _bootstrap_product_marketplace_status_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"product_marketplace_status_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM product_marketplace_status_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_product_marketplace_status_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            def _legacy_rows() -> List[Dict[str, Any]]:
                conn, _, _ = _pg_connect()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT product_id, yandex_present, yandex_status, ozon_present, ozon_status
                        FROM product_marketplace_status_rel
                        ORDER BY product_id
                        """
                    )
                    rows = cur.fetchall() or []
                return [
                    {
                        "product_id": str(row[0] or "").strip(),
                        "yandex_present": bool(row[1] or False),
                        "yandex_status": str(row[2] or "Нет данных").strip() or "Нет данных",
                        "ozon_present": bool(row[3] or False),
                        "ozon_status": str(row[4] or "Нет данных").strip() or "Нет данных",
                    }
                    for row in rows
                    if str(row[0] or "").strip()
                ]

            _replace_product_marketplace_status_tenant_table(_with_pg_retry(_legacy_rows), org_id)
    finally:
        lock.release()


def _collect_catalog_product_page_payload(rows: List[Dict[str, Any]]) -> List[tuple[Any, ...]]:
    payload: List[tuple[Any, ...]] = []
    for row in rows or []:
        product_id = str(row.get("product_id") or row.get("id") or "").strip()
        if not product_id:
            continue
        payload.append(
            (
                product_id,
                str(row.get("title") or row.get("name") or "").strip(),
                str(row.get("category_id") or "").strip(),
                str(row.get("category_path") or "").strip(),
                str(row.get("sku_pim") or "").strip() or None,
                str(row.get("sku_gt") or "").strip() or None,
                str(row.get("group_id") or "").strip() or None,
                str(row.get("group_name") or "").strip() or None,
                str(row.get("template_id") or "").strip() or None,
                str(row.get("template_name") or "").strip() or None,
                str(row.get("template_source_category_id") or "").strip() or None,
                bool(row.get("yandex_present") or False),
                str(row.get("yandex_status") or "Нет данных").strip() or "Нет данных",
                bool(row.get("ozon_present") or False),
                str(row.get("ozon_status") or "Нет данных").strip() or "Нет данных",
                str(row.get("preview_url") or "").strip() or None,
                json.dumps(row.get("exports_enabled") if isinstance(row.get("exports_enabled"), dict) else {}),
            )
        )
    return payload


def _replace_catalog_product_page_tenant_table(rows: List[Dict[str, Any]], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    payload = _collect_catalog_product_page_payload(rows)

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM catalog_product_page_tenant_rel WHERE organization_id = %s", [org_id])
            if payload:
                cur.executemany(
                    """
                    INSERT INTO catalog_product_page_tenant_rel (
                      organization_id, product_id, title, category_id, category_path, sku_pim, sku_gt, group_id, group_name,
                      template_id, template_name, template_source_category_id,
                      yandex_present, yandex_status, ozon_present, ozon_status,
                      preview_url, exports_enabled_json, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s,
                      %s, %s, %s, %s,
                      %s, %s::jsonb, NOW()
                    )
                    """,
                    [(org_id, *row) for row in payload],
                )

    _with_pg_retry(_run)


def _bootstrap_catalog_product_page_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"catalog_product_page_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM catalog_product_page_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        if org_id == DEFAULT_ORGANIZATION_ID:
            def _legacy_rows() -> List[Dict[str, Any]]:
                conn, _, _ = _pg_connect()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT
                          product_id, title, category_id, category_path, sku_pim, sku_gt, group_id, group_name,
                          template_id, template_name, template_source_category_id,
                          yandex_present, yandex_status, ozon_present, ozon_status,
                          preview_url, exports_enabled_json
                        FROM catalog_product_page_rel
                        ORDER BY title, product_id
                        """
                    )
                    rows = cur.fetchall() or []
                out: List[Dict[str, Any]] = []
                for row in rows:
                    exports_enabled = row[16] if isinstance(row[16], dict) else {}
                    out.append(
                        {
                            "product_id": str(row[0] or "").strip(),
                            "title": str(row[1] or "").strip(),
                            "category_id": str(row[2] or "").strip(),
                            "category_path": str(row[3] or "").strip(),
                            "sku_pim": str(row[4] or "").strip(),
                            "sku_gt": str(row[5] or "").strip(),
                            "group_id": str(row[6] or "").strip(),
                            "group_name": str(row[7] or "").strip(),
                            "template_id": str(row[8] or "").strip(),
                            "template_name": str(row[9] or "").strip(),
                            "template_source_category_id": str(row[10] or "").strip(),
                            "yandex_present": bool(row[11] or False),
                            "yandex_status": str(row[12] or "Нет данных").strip() or "Нет данных",
                            "ozon_present": bool(row[13] or False),
                            "ozon_status": str(row[14] or "Нет данных").strip() or "Нет данных",
                            "preview_url": str(row[15] or "").strip(),
                            "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                        }
                    )
                return [row for row in out if str(row.get("product_id") or "").strip()]

            _replace_catalog_product_page_tenant_table(_with_pg_retry(_legacy_rows), org_id)
    finally:
        lock.release()


def load_catalog_nodes() -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_catalog_nodes_from_legacy()

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, parent_id, name, position, template_id, products_count
                FROM catalog_nodes_rel
                ORDER BY COALESCE(parent_id, ''), position, name
                """
            )
            rows = cur.fetchall() or []
        return [
            {
                "id": str(row[0] or ""),
                "parent_id": str(row[1] or "").strip() or None,
                "name": str(row[2] or ""),
                "position": int(row[3] or 0),
                "template_id": str(row[4] or "").strip() or None,
                "products_count": int(row[5] or 0),
            }
            for row in rows
        ]

    return _with_pg_retry(_run)


def save_catalog_nodes(nodes: List[Dict[str, Any]]) -> None:
    _ensure_tables()
    _replace_catalog_nodes_table(nodes)


def load_category_mappings(organization_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_category_mappings_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Dict[str, str]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT catalog_category_id, provider, provider_category_id
                FROM category_mappings_tenant_rel
                WHERE organization_id = %s
                ORDER BY catalog_category_id, provider
                """,
                [org_id],
            )
            rows = cur.fetchall() or []
        out: Dict[str, Dict[str, str]] = {}
        for row in rows:
            cid = str(row[0] or "").strip()
            provider = str(row[1] or "").strip()
            provider_category_id = str(row[2] or "").strip()
            if not cid or not provider or not provider_category_id:
                continue
            out.setdefault(cid, {})[provider] = provider_category_id
        return out

    return _with_pg_retry(_run)


def save_category_mappings(items: Dict[str, Dict[str, str]], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    _replace_category_mappings_tenant_table(items, organization_id)


def load_attribute_mapping_doc(organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_attribute_mappings_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  catalog_category_id,
                  row_id,
                  catalog_name,
                  param_group,
                  confirmed,
                  yandex_param_id,
                  yandex_param_name,
                  yandex_kind,
                  yandex_values,
                  yandex_required,
                  yandex_export,
                  ozon_param_id,
                  ozon_param_name,
                  ozon_kind,
                  ozon_values,
                  ozon_required,
                  ozon_export,
                  updated_at
                FROM attribute_mappings_tenant_rel
                WHERE organization_id = %s
                ORDER BY catalog_category_id, catalog_name, row_id
                """,
                [org_id],
            )
            db_rows = cur.fetchall() or []

        items: Dict[str, Dict[str, Any]] = {}
        for row in db_rows:
            cid = str(row[0] or "").strip()
            if not cid:
                continue
            items.setdefault(cid, {"rows": [], "updated_at": None})
            updated_at = row[17].isoformat() if row[17] else None
            if updated_at and (items[cid].get("updated_at") or "") < updated_at:
                items[cid]["updated_at"] = updated_at
            items[cid]["rows"].append(
                {
                    "id": str(row[1] or "").strip(),
                    "catalog_name": str(row[2] or "").strip(),
                    "group": str(row[3] or "").strip(),
                    "confirmed": bool(row[4] or False),
                    "provider_map": {
                        "yandex_market": {
                            "id": str(row[5] or "").strip(),
                            "name": str(row[6] or "").strip(),
                            "kind": str(row[7] or "").strip(),
                            "values": list(row[8] or []),
                            "required": bool(row[9] or False),
                            "export": bool(row[10] or False),
                        },
                        "ozon": {
                            "id": str(row[11] or "").strip(),
                            "name": str(row[12] or "").strip(),
                            "kind": str(row[13] or "").strip(),
                            "values": list(row[14] or []),
                            "required": bool(row[15] or False),
                            "export": bool(row[16] or False),
                        },
                    },
                }
            )
        return {"version": 1, "items": items}

    return _with_pg_retry(_run)


def save_attribute_mapping_doc(doc: Dict[str, Any], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}}
    _replace_attribute_mappings_tenant_table(doc, organization_id)


def load_attribute_value_refs_doc(organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_attribute_value_refs_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  catalog_category_id,
                  catalog_name_key,
                  catalog_name,
                  param_group,
                  attribute_id,
                  dict_id,
                  value_type,
                  confirmed,
                  yandex_provider_category_id,
                  yandex_param_id,
                  yandex_param_name,
                  yandex_kind,
                  yandex_allowed_values,
                  yandex_required,
                  yandex_export,
                  ozon_provider_category_id,
                  ozon_param_id,
                  ozon_param_name,
                  ozon_kind,
                  ozon_allowed_values,
                  ozon_required,
                  ozon_export,
                  rows_count,
                  updated_at
                FROM attribute_value_refs_tenant_rel
                WHERE organization_id = %s
                ORDER BY catalog_category_id, catalog_name
                """,
                [org_id],
            )
            db_rows = cur.fetchall() or []

        items: Dict[str, Dict[str, Any]] = {}
        for row in db_rows:
            cid = str(row[0] or "").strip()
            if not cid:
                continue
            entry = items.setdefault(
                cid,
                {
                    "catalog_category_id": cid,
                    "providers": {
                        "yandex_market": {"provider_category_id": None, "parameters": {}, "params_count": 0},
                        "ozon": {"provider_category_id": None, "parameters": {}, "params_count": 0},
                    },
                    "catalog_params": {},
                    "rows_count": int(row[22] or 0),
                    "updated_at": None,
                },
            )
            updated_at = row[23].isoformat() if row[23] else None
            if updated_at and (entry.get("updated_at") or "") < updated_at:
                entry["updated_at"] = updated_at
            if row[8]:
                entry["providers"]["yandex_market"]["provider_category_id"] = str(row[8])
            if row[15]:
                entry["providers"]["ozon"]["provider_category_id"] = str(row[15])

            key = str(row[1] or "").strip() or str(row[2] or "").strip()
            entry["catalog_params"][key] = {
                "catalog_name": str(row[2] or "").strip(),
                "group": str(row[3] or "").strip(),
                "attribute_id": str(row[4] or "").strip() or None,
                "dict_id": str(row[5] or "").strip() or None,
                "type": str(row[6] or "").strip() or None,
                "confirmed": bool(row[7] or False),
                "bindings": {
                    "yandex_market": {
                        "id": str(row[9] or "").strip(),
                        "name": str(row[10] or "").strip(),
                        "kind": str(row[11] or "").strip(),
                        "values": list(row[12] or []),
                        "required": bool(row[13] or False),
                        "export": bool(row[14] or False),
                    },
                    "ozon": {
                        "id": str(row[16] or "").strip(),
                        "name": str(row[17] or "").strip(),
                        "kind": str(row[18] or "").strip(),
                        "values": list(row[19] or []),
                        "required": bool(row[20] or False),
                        "export": bool(row[21] or False),
                    },
                },
            }

        for payload in items.values():
            for provider in ("yandex_market", "ozon"):
                params = {}
                for raw in payload.get("catalog_params", {}).values():
                    bindings = raw.get("bindings") if isinstance(raw.get("bindings"), dict) else {}
                    binding = bindings.get(provider) if isinstance(bindings.get(provider), dict) else {}
                    pid = str(binding.get("id") or "").strip()
                    pname = str(binding.get("name") or "").strip()
                    if not pid and not pname:
                        continue
                    params[pid or pname] = {
                        "provider_param_id": pid or None,
                        "provider_param_name": pname or None,
                        "catalog_name": str(raw.get("catalog_name") or "").strip(),
                        "group": str(raw.get("group") or "").strip(),
                        "kind": str(binding.get("kind") or "").strip(),
                        "required": bool(binding.get("required") or False),
                        "allowed_values": list(binding.get("values") or []),
                        "export": bool(binding.get("export") or False),
                        "confirmed": bool(raw.get("confirmed") or False),
                    }
                payload["providers"][provider]["parameters"] = params
                payload["providers"][provider]["params_count"] = len(params)
        return {"version": 2, "updated_at": None, "items": items}

    return _with_pg_retry(_run)


def save_attribute_value_refs_doc(doc: Dict[str, Any], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    if not isinstance(doc, dict):
        doc = {"version": 2, "updated_at": None, "items": {}}
    _replace_attribute_value_refs_tenant_table(doc, organization_id)


def _slugify_code(value: str) -> str:
    raw = str(value or "").strip().lower()
    out: List[str] = []
    for ch in raw:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_"}:
            out.append("_")
    return "".join(out).strip("_") or "attr"


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _normalize_value_key(value: Any) -> str:
    return _normalize_text(value).lower().replace("ё", "е")


def _dictionary_default_doc(dict_id: str, title: str | None = None) -> Dict[str, Any]:
    did = str(dict_id or "").strip()
    now = ""
    code = did[len("dict_"):] if did.startswith("dict_") else _slugify_code(title or did)
    return {
        "id": did,
        "title": _normalize_text(title or did) or did,
        "code": code,
        "attr_id": f"attr_{code}_{did[-6:] or 'global'}",
        "type": "select",
        "scope": "both",
        "dict_id": did,
        "items": [],
        "aliases": {},
        "meta": {},
        "created_at": now,
        "updated_at": now,
    }


def _migrate_dict_items(items: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, str):
            value = _normalize_text(it)
            if value:
                out.append({"value": value, "count": 0, "last_seen": None, "sources": {}})
            continue
        if not isinstance(it, dict):
            continue
        value = _normalize_text(it.get("value"))
        if not value:
            continue
        out.append(
            {
                "value": value,
                "count": int(it.get("count") or 0),
                "last_seen": it.get("last_seen") or None,
                "sources": it.get("sources") if isinstance(it.get("sources"), dict) else {},
            }
        )
    return out


def _merge_dict_items(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for row in existing:
        key = _normalize_value_key(row.get("value"))
        if key:
            by_key[key] = row
    for row in incoming:
        key = _normalize_value_key(row.get("value"))
        if key and key not in by_key:
            by_key[key] = row
    return list(by_key.values())


def _normalize_dictionary_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        doc = {"version": 2, "items": []}
    items = doc.get("items")
    if not isinstance(items, list):
        items = []
    by_id: Dict[str, Dict[str, Any]] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        did = _normalize_text(raw.get("id"))
        if not did:
            continue
        title = _normalize_text(raw.get("title")) or did
        code = _normalize_text(raw.get("code")) or (did[len("dict_"):] if did.startswith("dict_") else _slugify_code(title))
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        incoming = {
            "id": did,
            "title": title,
            "code": code,
            "attr_id": _normalize_text(raw.get("attr_id")) or f"attr_{code}_{did[-6:] or 'global'}",
            "type": _normalize_text(raw.get("type")) or "select",
            "scope": _normalize_text(raw.get("scope")) or "both",
            "dict_id": did,
            "items": _migrate_dict_items(raw.get("items") if isinstance(raw.get("items"), list) else raw.get("values")),
            "aliases": raw.get("aliases") if isinstance(raw.get("aliases"), dict) else {},
            "meta": meta,
            "created_at": raw.get("created_at") or "",
            "updated_at": raw.get("updated_at") or "",
        }
        existing = by_id.get(did)
        if not existing:
            by_id[did] = incoming
            continue
        merged = dict(existing)
        merged["items"] = _merge_dict_items(existing.get("items", []), incoming.get("items", []))
        merged["aliases"] = {
            **(existing.get("aliases") if isinstance(existing.get("aliases"), dict) else {}),
            **(incoming.get("aliases") if isinstance(incoming.get("aliases"), dict) else {}),
        }
        merged["meta"] = {
            **(existing.get("meta") if isinstance(existing.get("meta"), dict) else {}),
            **(incoming.get("meta") if isinstance(incoming.get("meta"), dict) else {}),
        }
        if not _normalize_text(merged.get("title")) and _normalize_text(incoming.get("title")):
            merged["title"] = incoming["title"]
        if not _normalize_text(merged.get("attr_id")) and _normalize_text(incoming.get("attr_id")):
            merged["attr_id"] = incoming["attr_id"]
        if not _normalize_text(merged.get("created_at")) and _normalize_text(incoming.get("created_at")):
            merged["created_at"] = incoming["created_at"]
        if _normalize_text(incoming.get("updated_at")) and _normalize_text(merged.get("updated_at")) < _normalize_text(
            incoming.get("updated_at")
        ):
            merged["updated_at"] = incoming["updated_at"]
        by_id[did] = merged
    return {"version": 2, "items": list(by_id.values())}


def _load_legacy_dictionaries_doc() -> Dict[str, Any]:
    doc = read_doc(DICTIONARIES_PATH, default={"version": 2, "items": []})
    normalized = _normalize_dictionary_doc(doc if isinstance(doc, dict) else {"version": 2, "items": []})
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    by_id: Dict[str, Dict[str, Any]] = {
        str(item.get("id") or "").strip(): item for item in items if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    try:
        for path in DICTS_DIR.glob("*.json"):
            raw = read_doc(path, default={})
            if not isinstance(raw, dict):
                continue
            did = _normalize_text(raw.get("id")) or path.stem
            title = _normalize_text(raw.get("title")) or did
            incoming = {
                "id": did,
                "title": title,
                "code": _normalize_text(raw.get("code")) or (did[len("dict_"):] if did.startswith("dict_") else _slugify_code(title)),
                "attr_id": _normalize_text(raw.get("attr_id")),
                "type": _normalize_text(raw.get("type")) or "select",
                "scope": _normalize_text(raw.get("scope")) or "both",
                "dict_id": did,
                "items": _migrate_dict_items(raw.get("items")),
                "aliases": raw.get("aliases") if isinstance(raw.get("aliases"), dict) else {},
                "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
                "created_at": raw.get("created_at") or "",
                "updated_at": raw.get("updated_at") or "",
            }
            existing = by_id.get(did)
            if not existing:
                by_id[did] = incoming
                continue
            merged = dict(existing)
            merged["items"] = _merge_dict_items(existing.get("items", []), incoming.get("items", []))
            existing_aliases = existing.get("aliases") if isinstance(existing.get("aliases"), dict) else {}
            incoming_aliases = incoming.get("aliases") if isinstance(incoming.get("aliases"), dict) else {}
            merged["aliases"] = {**existing_aliases, **incoming_aliases}
            existing_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
            incoming_meta = incoming.get("meta") if isinstance(incoming.get("meta"), dict) else {}
            merged["meta"] = {**existing_meta, **incoming_meta}
            if not _normalize_text(merged.get("title")) and _normalize_text(incoming.get("title")):
                merged["title"] = incoming.get("title")
            if not _normalize_text(merged.get("attr_id")) and _normalize_text(incoming.get("attr_id")):
                merged["attr_id"] = incoming.get("attr_id")
            by_id[did] = merged
    except Exception:
        pass
    return {"version": 2, "items": list(by_id.values())}


def _replace_dictionaries_tables(doc: Dict[str, Any]) -> None:
    normalized = _normalize_dictionary_doc(doc)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    dictionaries_rows: List[tuple[Any, ...]] = []
    value_rows_map: Dict[tuple[str, str], Dict[str, Any]] = {}
    source_rows_map: Dict[tuple[str, str, str], int] = {}
    alias_rows_map: Dict[tuple[str, str], str] = {}
    provider_rows_map: Dict[tuple[str, str], tuple[Any, ...]] = {}
    export_rows_map: Dict[tuple[str, str, str], str] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        did = _normalize_text(item.get("id"))
        if not did:
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        dictionaries_rows.append(
            (
                did,
                _normalize_text(item.get("title")) or did,
                _normalize_text(item.get("code")) or (did[len("dict_"):] if did.startswith("dict_") else _slugify_code(item.get("title"))),
                _normalize_text(item.get("attr_id")) or f"attr_{did}",
                _normalize_text(item.get("type")) or "select",
                _normalize_text(item.get("scope")) or "both",
                bool(meta.get("service") or False),
                bool(meta.get("required") or False),
                _normalize_text(meta.get("param_group")) or None,
                _normalize_text(meta.get("template_layer")) or None,
                str(item.get("created_at") or "") or None,
                str(item.get("updated_at") or "") or None,
            )
        )

        for position, raw_value in enumerate(_migrate_dict_items(item.get("items"))):
            value_key = _normalize_value_key(raw_value.get("value"))
            if not value_key:
                continue
            row_key = (did, value_key)
            next_value = {
                "value_text": _normalize_text(raw_value.get("value")),
                "value_count": int(raw_value.get("count") or 0),
                "last_seen": str(raw_value.get("last_seen") or "") or None,
                "position": int(position),
            }
            existing_value = value_rows_map.get(row_key)
            if not existing_value:
                value_rows_map[row_key] = next_value
            else:
                existing_value["value_count"] = int(existing_value.get("value_count") or 0) + next_value["value_count"]
                if next_value["last_seen"] and (existing_value.get("last_seen") or "") < next_value["last_seen"]:
                    existing_value["last_seen"] = next_value["last_seen"]
                if len(next_value["value_text"]) > len(str(existing_value.get("value_text") or "")):
                    existing_value["value_text"] = next_value["value_text"]
                existing_value["position"] = min(int(existing_value.get("position") or 0), next_value["position"])
            sources = raw_value.get("sources") if isinstance(raw_value.get("sources"), dict) else {}
            for source_name, source_count in sources.items():
                sname = _normalize_text(source_name)
                if not sname:
                    continue
                source_key = (did, value_key, sname)
                source_rows_map[source_key] = int(source_rows_map.get(source_key) or 0) + int(source_count or 0)

        aliases = item.get("aliases") if isinstance(item.get("aliases"), dict) else {}
        for alias_key, canonical_value in aliases.items():
            akey = _normalize_value_key(alias_key)
            cval = _normalize_text(canonical_value)
            if akey and cval:
                alias_rows_map[(did, akey)] = cval

        source_reference = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
        for provider, payload in source_reference.items():
            if not isinstance(payload, dict):
                continue
            pname = _normalize_text(provider)
            if not pname:
                continue
            provider_rows_map[(did, pname)] = (
                did,
                pname,
                _normalize_text(payload.get("id")) or None,
                _normalize_text(payload.get("name")) or None,
                _normalize_text(payload.get("kind")) or None,
                bool(payload.get("required") or False),
                [str(v).strip() for v in (payload.get("allowed_values") or []) if str(v).strip()] or None,
            )

        export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
        for provider, mapping in export_map.items():
            if not isinstance(mapping, dict):
                continue
            pname = _normalize_text(provider)
            if not pname:
                continue
            for canonical_key, provider_value in mapping.items():
                ckey = _normalize_value_key(canonical_key)
                pvalue = _normalize_text(provider_value)
                if ckey and pvalue:
                    export_rows_map[(did, pname, ckey)] = pvalue

    value_rows: List[tuple[Any, ...]] = [
        (
            dict_id,
            value_key,
            str(payload.get("value_text") or ""),
            int(payload.get("value_count") or 0),
            payload.get("last_seen"),
            int(payload.get("position") or 0),
        )
        for (dict_id, value_key), payload in value_rows_map.items()
    ]
    source_rows: List[tuple[Any, ...]] = [
        (dict_id, value_key, source_name, int(source_count or 0))
        for (dict_id, value_key, source_name), source_count in source_rows_map.items()
    ]
    alias_rows: List[tuple[Any, ...]] = [
        (dict_id, alias_key, canonical_value)
        for (dict_id, alias_key), canonical_value in alias_rows_map.items()
    ]
    provider_rows: List[tuple[Any, ...]] = list(provider_rows_map.values())
    export_rows: List[tuple[Any, ...]] = [
        (dict_id, provider, canonical_key, provider_value)
        for (dict_id, provider, canonical_key), provider_value in export_rows_map.items()
    ]

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dictionary_export_maps_rel")
            cur.execute("DELETE FROM dictionary_provider_refs_rel")
            cur.execute("DELETE FROM dictionary_aliases_rel")
            cur.execute("DELETE FROM dictionary_value_sources_rel")
            cur.execute("DELETE FROM dictionary_values_rel")
            cur.execute("DELETE FROM dictionaries_rel")
            if dictionaries_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionaries_rel (
                      id, title, code, attr_id, attr_type, scope,
                      is_service, is_required, param_group, template_layer, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    dictionaries_rows,
                )
            if value_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_values_rel (
                      dict_id, value_key, value_text, value_count, last_seen, position
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    value_rows,
                )
            if source_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_value_sources_rel (
                      dict_id, value_key, source_name, source_count
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    source_rows,
                )
            if alias_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_aliases_rel (
                      dict_id, alias_key, canonical_value
                    ) VALUES (%s, %s, %s)
                    """,
                    alias_rows,
                )
            if provider_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_provider_refs_rel (
                      dict_id, provider, provider_param_id, provider_param_name, kind, is_required, allowed_values
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    provider_rows,
                )
            if export_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_export_maps_rel (
                      dict_id, provider, canonical_key, provider_value
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    export_rows,
                )

    _with_pg_retry(_run)


def _replace_dictionaries_tenant_tables(doc: Dict[str, Any], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    normalized = _normalize_dictionary_doc(doc)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    dictionaries_rows: List[tuple[Any, ...]] = []
    value_rows_map: Dict[tuple[str, str], Dict[str, Any]] = {}
    source_rows_map: Dict[tuple[str, str, str], int] = {}
    alias_rows_map: Dict[tuple[str, str], str] = {}
    provider_rows_map: Dict[tuple[str, str], tuple[Any, ...]] = {}
    export_rows_map: Dict[tuple[str, str, str], str] = {}

    for item in items:
        if not isinstance(item, dict):
            continue
        did = _normalize_text(item.get("id"))
        if not did:
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        dictionaries_rows.append(
            (
                org_id,
                did,
                _normalize_text(item.get("title")) or did,
                _normalize_text(item.get("code")) or (did[len("dict_"):] if did.startswith("dict_") else _slugify_code(item.get("title"))),
                _normalize_text(item.get("attr_id")) or f"attr_{did}",
                _normalize_text(item.get("type")) or "select",
                _normalize_text(item.get("scope")) or "both",
                bool(meta.get("service") or False),
                bool(meta.get("required") or False),
                _normalize_text(meta.get("param_group")) or None,
                _normalize_text(meta.get("template_layer")) or None,
                str(item.get("created_at") or "") or None,
                str(item.get("updated_at") or "") or None,
            )
        )

        for position, raw_value in enumerate(_migrate_dict_items(item.get("items"))):
            value_key = _normalize_value_key(raw_value.get("value"))
            if not value_key:
                continue
            row_key = (did, value_key)
            next_value = {
                "value_text": _normalize_text(raw_value.get("value")),
                "value_count": int(raw_value.get("count") or 0),
                "last_seen": str(raw_value.get("last_seen") or "") or None,
                "position": int(position),
            }
            existing_value = value_rows_map.get(row_key)
            if not existing_value:
                value_rows_map[row_key] = next_value
            else:
                existing_value["value_count"] = int(existing_value.get("value_count") or 0) + next_value["value_count"]
                if next_value["last_seen"] and (existing_value.get("last_seen") or "") < next_value["last_seen"]:
                    existing_value["last_seen"] = next_value["last_seen"]
                if len(next_value["value_text"]) > len(str(existing_value.get("value_text") or "")):
                    existing_value["value_text"] = next_value["value_text"]
                existing_value["position"] = min(int(existing_value.get("position") or 0), next_value["position"])
            sources = raw_value.get("sources") if isinstance(raw_value.get("sources"), dict) else {}
            for source_name, source_count in sources.items():
                sname = _normalize_text(source_name)
                if not sname:
                    continue
                source_key = (did, value_key, sname)
                source_rows_map[source_key] = int(source_rows_map.get(source_key) or 0) + int(source_count or 0)

        aliases = item.get("aliases") if isinstance(item.get("aliases"), dict) else {}
        for alias_key, canonical_value in aliases.items():
            akey = _normalize_value_key(alias_key)
            cval = _normalize_text(canonical_value)
            if akey and cval:
                alias_rows_map[(did, akey)] = cval

        source_reference = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
        for provider, payload in source_reference.items():
            if not isinstance(payload, dict):
                continue
            pname = _normalize_text(provider)
            if not pname:
                continue
            provider_rows_map[(did, pname)] = (
                org_id,
                did,
                pname,
                _normalize_text(payload.get("id")) or None,
                _normalize_text(payload.get("name")) or None,
                _normalize_text(payload.get("kind")) or None,
                bool(payload.get("required") or False),
                [str(v).strip() for v in (payload.get("allowed_values") or []) if str(v).strip()] or None,
            )

        export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
        for provider, mapping in export_map.items():
            if not isinstance(mapping, dict):
                continue
            pname = _normalize_text(provider)
            if not pname:
                continue
            for canonical_key, provider_value in mapping.items():
                ckey = _normalize_value_key(canonical_key)
                pvalue = _normalize_text(provider_value)
                if ckey and pvalue:
                    export_rows_map[(did, pname, ckey)] = pvalue

    value_rows: List[tuple[Any, ...]] = [
        (
            org_id,
            dict_id,
            value_key,
            str(payload.get("value_text") or ""),
            int(payload.get("value_count") or 0),
            payload.get("last_seen"),
            int(payload.get("position") or 0),
        )
        for (dict_id, value_key), payload in value_rows_map.items()
    ]
    source_rows: List[tuple[Any, ...]] = [
        (org_id, dict_id, value_key, source_name, int(source_count or 0))
        for (dict_id, value_key, source_name), source_count in source_rows_map.items()
    ]
    alias_rows: List[tuple[Any, ...]] = [
        (org_id, dict_id, alias_key, canonical_value)
        for (dict_id, alias_key), canonical_value in alias_rows_map.items()
    ]
    export_rows: List[tuple[Any, ...]] = [
        (org_id, dict_id, provider, canonical_key, provider_value)
        for (dict_id, provider, canonical_key), provider_value in export_rows_map.items()
    ]

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM dictionary_export_maps_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM dictionary_provider_refs_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM dictionary_aliases_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM dictionary_value_sources_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM dictionary_values_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM dictionaries_tenant_rel WHERE organization_id = %s", [org_id])
            if dictionaries_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionaries_tenant_rel (
                      organization_id, id, title, code, attr_id, attr_type, scope,
                      is_service, is_required, param_group, template_layer, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    dictionaries_rows,
                )
            if value_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_values_tenant_rel (
                      organization_id, dict_id, value_key, value_text, value_count, last_seen, position
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    value_rows,
                )
            if source_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_value_sources_tenant_rel (
                      organization_id, dict_id, value_key, source_name, source_count
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    source_rows,
                )
            if alias_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_aliases_tenant_rel (
                      organization_id, dict_id, alias_key, canonical_value
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    alias_rows,
                )
            if provider_rows_map:
                cur.executemany(
                    """
                    INSERT INTO dictionary_provider_refs_tenant_rel (
                      organization_id, dict_id, provider, provider_param_id, provider_param_name, kind, is_required, allowed_values
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    list(provider_rows_map.values()),
                )
            if export_rows:
                cur.executemany(
                    """
                    INSERT INTO dictionary_export_maps_tenant_rel (
                      organization_id, dict_id, provider, canonical_key, provider_value
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    export_rows,
                )

    _with_pg_retry(_run)


def _bootstrap_dictionaries_from_legacy() -> None:
    lock = with_lock("dictionaries_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("dictionaries_rel") > 0:
            return
        doc = _load_legacy_dictionaries_doc()
        _replace_dictionaries_tables(doc)
    finally:
        lock.release()


def _bootstrap_dictionaries_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"dictionaries_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM dictionaries_tenant_rel WHERE organization_id = %s", [org_id])
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_dictionaries_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            doc = _load_legacy_dictionaries_doc()
            save_dictionaries_db_doc(doc, org_id)
    finally:
        lock.release()


def load_dictionaries_db_doc(organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_dictionaries_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, title, code, attr_id, attr_type, scope,
                  is_service, is_required, param_group, template_layer, created_at, updated_at
                FROM dictionaries_tenant_rel
                WHERE organization_id = %s
                ORDER BY LOWER(title), id
                """,
                [org_id],
            )
            dict_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, value_key, value_text, value_count, last_seen, position
                FROM dictionary_values_tenant_rel
                WHERE organization_id = %s
                ORDER BY dict_id, position, value_text
                """,
                [org_id],
            )
            value_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, value_key, source_name, source_count
                FROM dictionary_value_sources_tenant_rel
                WHERE organization_id = %s
                ORDER BY dict_id, value_key, source_name
                """,
                [org_id],
            )
            source_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, alias_key, canonical_value
                FROM dictionary_aliases_tenant_rel
                WHERE organization_id = %s
                ORDER BY dict_id, alias_key
                """,
                [org_id],
            )
            alias_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, provider, provider_param_id, provider_param_name, kind, is_required, allowed_values
                FROM dictionary_provider_refs_tenant_rel
                WHERE organization_id = %s
                ORDER BY dict_id, provider
                """,
                [org_id],
            )
            provider_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, provider, canonical_key, provider_value
                FROM dictionary_export_maps_tenant_rel
                WHERE organization_id = %s
                ORDER BY dict_id, provider, canonical_key
                """,
                [org_id],
            )
            export_rows = cur.fetchall() or []

        source_map: Dict[tuple[str, str], Dict[str, int]] = {}
        for row in source_rows:
            source_map.setdefault((str(row[0] or ""), str(row[1] or "")), {})[str(row[2] or "")] = int(row[3] or 0)

        values_map: Dict[str, List[Dict[str, Any]]] = {}
        for row in value_rows:
            did = str(row[0] or "")
            value_key = str(row[1] or "")
            values_map.setdefault(did, []).append(
                {
                    "value": str(row[2] or ""),
                    "count": int(row[3] or 0),
                    "last_seen": str(row[4] or "") or None,
                    "sources": source_map.get((did, value_key), {}),
                }
            )

        aliases_map: Dict[str, Dict[str, str]] = {}
        for row in alias_rows:
            aliases_map.setdefault(str(row[0] or ""), {})[str(row[1] or "")] = str(row[2] or "")

        provider_ref_map: Dict[str, Dict[str, Any]] = {}
        for row in provider_rows:
            did = str(row[0] or "")
            provider_ref_map.setdefault(did, {})[str(row[1] or "")] = {
                "id": str(row[2] or "") or None,
                "name": str(row[3] or "") or None,
                "kind": str(row[4] or "") or None,
                "required": bool(row[5] or False),
                "allowed_values": list(row[6] or []),
            }

        export_map: Dict[str, Dict[str, Dict[str, str]]] = {}
        for row in export_rows:
            did = str(row[0] or "")
            provider = str(row[1] or "")
            export_map.setdefault(did, {}).setdefault(provider, {})[str(row[2] or "")] = str(row[3] or "")

        items: List[Dict[str, Any]] = []
        for row in dict_rows:
            did = str(row[0] or "")
            meta: Dict[str, Any] = {}
            if bool(row[6] or False):
                meta["service"] = True
            if bool(row[7] or False):
                meta["required"] = True
            if str(row[8] or "").strip():
                meta["param_group"] = str(row[8] or "").strip()
            if str(row[9] or "").strip():
                meta["template_layer"] = str(row[9] or "").strip()
            if provider_ref_map.get(did):
                meta["source_reference"] = provider_ref_map[did]
            if export_map.get(did):
                meta["export_map"] = export_map[did]
            items.append(
                {
                    "id": did,
                    "title": str(row[1] or ""),
                    "code": str(row[2] or ""),
                    "attr_id": str(row[3] or ""),
                    "type": str(row[4] or "") or "select",
                    "scope": str(row[5] or "") or "both",
                    "dict_id": did,
                    "items": values_map.get(did, []),
                    "aliases": aliases_map.get(did, {}),
                    "meta": meta,
                    "created_at": str(row[10] or "") or "",
                    "updated_at": str(row[11] or "") or "",
                }
            )
        return {"version": 2, "items": items}

    return _with_pg_retry(_run)


def save_dictionaries_db_doc(doc: Dict[str, Any], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    normalized = _normalize_dictionary_doc(doc)
    lock = with_lock(f"dictionaries_tenant_rel_write:{org_id}")
    lock.acquire()
    try:
        _replace_dictionaries_tenant_tables(normalized, org_id)
    finally:
        lock.release()


def _dedupe_list_str(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _normalize_templates_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        doc = {"version": 2, "templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
    templates = doc.get("templates") if isinstance(doc.get("templates"), dict) else {}
    attributes = doc.get("attributes") if isinstance(doc.get("attributes"), dict) else {}
    category_to_template = doc.get("category_to_template") if isinstance(doc.get("category_to_template"), dict) else {}
    category_to_templates = doc.get("category_to_templates") if isinstance(doc.get("category_to_templates"), dict) else {}

    normalized_templates: Dict[str, Dict[str, Any]] = {}
    for key, value in templates.items():
        if not isinstance(value, dict):
            continue
        tid = str(value.get("id") or key).strip()
        if not tid:
            continue
        normalized_templates[tid] = {
            **value,
            "id": tid,
            "name": str(value.get("name") or tid).strip() or tid,
            "category_id": str(value.get("category_id") or "").strip() or None,
            "created_at": value.get("created_at") or "",
            "updated_at": value.get("updated_at") or "",
        }

    normalized_attributes: Dict[str, List[Dict[str, Any]]] = {}
    for key, value in attributes.items():
        tid = str(key).strip()
        if not tid:
            continue
        rows = value if isinstance(value, list) else []
        next_rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            next_rows.append(
                {
                    **row,
                    "id": str(row.get("id") or "").strip() or f"{tid}:{idx}",
                    "name": str(row.get("name") or row.get("code") or "").strip(),
                    "code": str(row.get("code") or "").strip(),
                    "type": str(row.get("type") or "text").strip() or "text",
                    "required": bool(row.get("required") or False),
                    "scope": str(row.get("scope") or "common").strip() or "common",
                    "attribute_id": str(row.get("attribute_id") or "").strip() or None,
                    "position": int(row.get("position") or idx),
                    "locked": bool(row.get("locked") or False),
                    "options": row.get("options") if isinstance(row.get("options"), dict) else {},
                }
            )
        normalized_attributes[tid] = next_rows

    normalized_cat_to_tpls: Dict[str, List[str]] = {}
    for cid, tids in category_to_templates.items():
        cid_s = str(cid).strip()
        if not cid_s:
            continue
        normalized_cat_to_tpls[cid_s] = _dedupe_list_str(tids)
    for cid, tid in category_to_template.items():
        cid_s = str(cid).strip()
        tid_s = str(tid).strip()
        if not cid_s or not tid_s:
            continue
        normalized_cat_to_tpls.setdefault(cid_s, [])
        if tid_s not in normalized_cat_to_tpls[cid_s]:
            normalized_cat_to_tpls[cid_s].insert(0, tid_s)

    normalized_cat_to_tpl: Dict[str, str] = {}
    for cid, tids in normalized_cat_to_tpls.items():
        if tids:
            normalized_cat_to_tpl[cid] = tids[0]

    return {
        "version": 2,
        "templates": normalized_templates,
        "attributes": normalized_attributes,
        "category_to_template": normalized_cat_to_tpl,
        "category_to_templates": normalized_cat_to_tpls,
    }


def _replace_templates_tables(doc: Dict[str, Any]) -> None:
    normalized = _normalize_templates_doc(doc)
    templates = normalized.get("templates") if isinstance(normalized.get("templates"), dict) else {}
    attributes = normalized.get("attributes") if isinstance(normalized.get("attributes"), dict) else {}
    category_to_templates = normalized.get("category_to_templates") if isinstance(normalized.get("category_to_templates"), dict) else {}

    template_rows: List[tuple[Any, ...]] = []
    attr_rows: List[tuple[Any, ...]] = []
    link_rows: List[tuple[Any, ...]] = []

    for tid, template in templates.items():
        if not isinstance(template, dict):
            continue
        template_rows.append(
            (
                str(tid).strip(),
                str(template.get("name") or tid).strip() or str(tid).strip(),
                str(template.get("category_id") or "").strip() or None,
                str(template.get("created_at") or "") or None,
                str(template.get("updated_at") or "") or None,
            )
        )

    for tid, rows in attributes.items():
        tid_s = str(tid).strip()
        if not tid_s or not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            attr_rows.append(
                (
                    tid_s,
                    str(row.get("id") or "").strip() or f"{tid_s}:{idx}",
                    str(row.get("name") or row.get("code") or "").strip(),
                    str(row.get("code") or "").strip(),
                    str(row.get("type") or "text").strip() or "text",
                    bool(row.get("required") or False),
                    str(row.get("scope") or "common").strip() or "common",
                    str(row.get("attribute_id") or "").strip() or None,
                    int(row.get("position") or idx),
                    bool(row.get("locked") or False),
                    json.dumps(row.get("options") if isinstance(row.get("options"), dict) else {}, ensure_ascii=False),
                )
            )

    for cid, tids in category_to_templates.items():
        cid_s = str(cid).strip()
        if not cid_s or not isinstance(tids, list):
            continue
        for position, tid in enumerate(tids):
            tid_s = str(tid).strip()
            if cid_s and tid_s:
                link_rows.append((cid_s, tid_s, int(position)))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_template_links_rel")
            cur.execute("DELETE FROM template_attributes_rel")
            cur.execute("DELETE FROM templates_rel")
            if template_rows:
                cur.executemany(
                    """
                    INSERT INTO templates_rel (
                      id, name, category_id, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    template_rows,
                )
            if attr_rows:
                cur.executemany(
                    """
                    INSERT INTO template_attributes_rel (
                      template_id, attr_id, name, code, attr_type, is_required,
                      scope, attribute_id, position, is_locked, options_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    attr_rows,
                )
            if link_rows:
                cur.executemany(
                    """
                    INSERT INTO category_template_links_rel (
                      category_id, template_id, position
                    ) VALUES (%s, %s, %s)
                    """,
                    link_rows,
                )

    _with_pg_retry(_run)


def _replace_templates_tenant_tables(doc: Dict[str, Any], organization_id: Optional[str]) -> None:
    org_id = _resolve_organization_id(organization_id)
    normalized = _normalize_templates_doc(doc)
    templates = normalized.get("templates") if isinstance(normalized.get("templates"), dict) else {}
    attributes = normalized.get("attributes") if isinstance(normalized.get("attributes"), dict) else {}
    category_to_templates = normalized.get("category_to_templates") if isinstance(normalized.get("category_to_templates"), dict) else {}

    template_rows: List[tuple[Any, ...]] = []
    attr_rows: List[tuple[Any, ...]] = []
    link_rows: List[tuple[Any, ...]] = []

    for tid, template in templates.items():
        if not isinstance(template, dict):
            continue
        template_rows.append(
            (
                org_id,
                str(tid).strip(),
                str(template.get("name") or tid).strip() or str(tid).strip(),
                str(template.get("category_id") or "").strip() or None,
                str(template.get("created_at") or "") or None,
                str(template.get("updated_at") or "") or None,
            )
        )

    for tid, rows in attributes.items():
        tid_s = str(tid).strip()
        if not tid_s or not isinstance(rows, list):
            continue
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            attr_rows.append(
                (
                    org_id,
                    tid_s,
                    str(row.get("id") or "").strip() or f"{tid_s}:{idx}",
                    str(row.get("name") or row.get("code") or "").strip(),
                    str(row.get("code") or "").strip(),
                    str(row.get("type") or "text").strip() or "text",
                    bool(row.get("required") or False),
                    str(row.get("scope") or "common").strip() or "common",
                    str(row.get("attribute_id") or "").strip() or None,
                    int(row.get("position") or idx),
                    bool(row.get("locked") or False),
                    json.dumps(row.get("options") if isinstance(row.get("options"), dict) else {}, ensure_ascii=False),
                )
            )

    for cid, tids in category_to_templates.items():
        cid_s = str(cid).strip()
        if not cid_s or not isinstance(tids, list):
            continue
        for position, tid in enumerate(tids):
            tid_s = str(tid).strip()
            if cid_s and tid_s:
                link_rows.append((org_id, cid_s, tid_s, int(position)))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_template_links_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM template_attributes_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM templates_tenant_rel WHERE organization_id = %s", [org_id])
            if template_rows:
                cur.executemany(
                    """
                    INSERT INTO templates_tenant_rel (
                      organization_id, id, name, category_id, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    template_rows,
                )
            if attr_rows:
                cur.executemany(
                    """
                    INSERT INTO template_attributes_tenant_rel (
                      organization_id, template_id, attr_id, name, code, attr_type, is_required,
                      scope, attribute_id, position, is_locked, options_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    attr_rows,
                )
            if link_rows:
                cur.executemany(
                    """
                    INSERT INTO category_template_links_tenant_rel (
                      organization_id, category_id, template_id, position
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    link_rows,
                )

    _with_pg_retry(_run)


def save_template_category_doc(
    catalog_category_id: str,
    template: Dict[str, Any],
    attributes: List[Dict[str, Any]],
    category_template_ids: List[str],
    organization_id: Optional[str] = None,
) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    cid = str(catalog_category_id or "").strip()
    if not cid:
        return

    template_id = str((template or {}).get("id") or "").strip()
    template_rows: List[tuple[Any, ...]] = []
    if template_id and isinstance(template, dict):
        template_rows.append(
            (
                org_id,
                template_id,
                str(template.get("name") or template_id).strip() or template_id,
                cid,
                str(template.get("created_at") or "") or None,
                str(template.get("updated_at") or "") or None,
            )
        )

    attr_rows: List[tuple[Any, ...]] = []
    for idx, row in enumerate(attributes or []):
        if not isinstance(row, dict) or not template_id:
            continue
        attr_rows.append(
            (
                org_id,
                template_id,
                str(row.get("id") or "").strip() or f"{template_id}:{idx}",
                str(row.get("name") or row.get("code") or "").strip(),
                str(row.get("code") or "").strip(),
                str(row.get("type") or "text").strip() or "text",
                bool(row.get("required") or False),
                str(row.get("scope") or "common").strip() or "common",
                str(row.get("attribute_id") or "").strip() or None,
                int(row.get("position") or idx),
                bool(row.get("locked") or False),
                json.dumps(row.get("options") if isinstance(row.get("options"), dict) else {}, ensure_ascii=False),
            )
        )

    link_rows: List[tuple[Any, ...]] = []
    next_template_ids = [str(tid or "").strip() for tid in (category_template_ids or []) if str(tid or "").strip()]
    for position, tid in enumerate(next_template_ids):
        link_rows.append((org_id, cid, tid, int(position)))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM templates_tenant_rel
                WHERE organization_id = %s AND category_id = %s
                """,
                [org_id, cid],
            )
            legacy_template_ids = [str((row or [None])[0] or "").strip() for row in cur.fetchall() or []]
            legacy_template_ids = [tid for tid in legacy_template_ids if tid]

            cur.execute(
                """
                DELETE FROM category_template_links_tenant_rel
                WHERE organization_id = %s AND category_id = %s
                """,
                [org_id, cid],
            )
            if legacy_template_ids:
                cur.execute(
                    """
                    DELETE FROM template_attributes_tenant_rel
                    WHERE organization_id = %s AND template_id = ANY(%s)
                    """,
                    [org_id, legacy_template_ids],
                )
                cur.execute(
                    """
                    DELETE FROM templates_tenant_rel
                    WHERE organization_id = %s AND id = ANY(%s)
                    """,
                    [org_id, legacy_template_ids],
                )
            if template_rows:
                cur.executemany(
                    """
                    INSERT INTO templates_tenant_rel (
                      organization_id, id, name, category_id, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    template_rows,
                )
            if attr_rows:
                cur.executemany(
                    """
                    INSERT INTO template_attributes_tenant_rel (
                      organization_id, template_id, attr_id, name, code, attr_type, is_required,
                      scope, attribute_id, position, is_locked, options_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    attr_rows,
                )
            if link_rows:
                cur.executemany(
                    """
                    INSERT INTO category_template_links_tenant_rel (
                      organization_id, category_id, template_id, position
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    link_rows,
                )

    _with_pg_retry(_run)


def _bootstrap_templates_from_legacy() -> None:
    lock = with_lock("templates_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("templates_rel") > 0:
            return
        doc = read_doc(TEMPLATES_PATH, default={"version": 2, "templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}})
        _replace_templates_tables(doc if isinstance(doc, dict) else {})
    finally:
        lock.release()


def _bootstrap_templates_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    with _TEMPLATES_TENANT_READY_LOCK:
        if org_id in _TEMPLATES_TENANT_READY:
            return
    lock = with_lock(f"templates_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        with _TEMPLATES_TENANT_READY_LOCK:
            if org_id in _TEMPLATES_TENANT_READY:
                return
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM templates_tenant_rel WHERE organization_id = %s", [org_id])
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            with _TEMPLATES_TENANT_READY_LOCK:
                _TEMPLATES_TENANT_READY.add(org_id)
            return
        _bootstrap_templates_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            doc = read_doc(
                TEMPLATES_PATH,
                default={"version": 2, "templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}},
            )
            _replace_templates_tenant_tables(doc if isinstance(doc, dict) else {}, org_id)
        with _TEMPLATES_TENANT_READY_LOCK:
            _TEMPLATES_TENANT_READY.add(org_id)
    finally:
        lock.release()


def load_templates_db_doc(organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_templates_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, category_id, created_at, updated_at
                FROM templates_tenant_rel
                WHERE organization_id = %s
                ORDER BY id
                """,
                [org_id],
            )
            template_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT template_id, attr_id, name, code, attr_type, is_required,
                       scope, attribute_id, position, is_locked, options_json
                FROM template_attributes_tenant_rel
                WHERE organization_id = %s
                ORDER BY template_id, position, code
                """,
                [org_id],
            )
            attr_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT category_id, template_id, position
                FROM category_template_links_tenant_rel
                WHERE organization_id = %s
                ORDER BY category_id, position, template_id
                """,
                [org_id],
            )
            link_rows = cur.fetchall() or []

        templates: Dict[str, Dict[str, Any]] = {}
        for row in template_rows:
            tid = str(row[0] or "").strip()
            if not tid:
                continue
            templates[tid] = {
                "id": tid,
                "name": str(row[1] or tid).strip() or tid,
                "category_id": str(row[2] or "").strip() or None,
                "created_at": str(row[3] or "") or "",
                "updated_at": str(row[4] or "") or "",
            }

        attributes: Dict[str, List[Dict[str, Any]]] = {}
        for row in attr_rows:
            tid = str(row[0] or "").strip()
            if not tid:
                continue
            options = row[10] if isinstance(row[10], dict) else {}
            if not isinstance(options, dict):
                try:
                    options = json.loads(str(row[10] or "{}"))
                except Exception:
                    options = {}
            attributes.setdefault(tid, []).append(
                {
                    "id": str(row[1] or "").strip(),
                    "name": str(row[2] or "").strip(),
                    "code": str(row[3] or "").strip(),
                    "type": str(row[4] or "text").strip() or "text",
                    "required": bool(row[5] or False),
                    "scope": str(row[6] or "common").strip() or "common",
                    "attribute_id": str(row[7] or "").strip() or None,
                    "position": int(row[8] or 0),
                    "locked": bool(row[9] or False),
                    "options": options if isinstance(options, dict) else {},
                }
            )

        category_to_templates: Dict[str, List[str]] = {}
        for row in link_rows:
            cid = str(row[0] or "").strip()
            tid = str(row[1] or "").strip()
            if cid and tid:
                category_to_templates.setdefault(cid, []).append(tid)

        category_to_template: Dict[str, str] = {}
        for cid, tids in category_to_templates.items():
            if tids:
                category_to_template[cid] = tids[0]

        return {
            "version": 2,
            "templates": templates,
            "attributes": attributes,
            "category_to_template": category_to_template,
            "category_to_templates": category_to_templates,
        }
    return _normalize_templates_doc(_with_pg_retry(_run))


def load_template_editor_payload(category_path_ids: List[str], organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_templates_tenant_from_legacy(org_id)
    path_ids = [str(item or "").strip() for item in category_path_ids if str(item or "").strip()]
    if not path_ids:
        return {"template": None, "attributes": [], "owner_category_id": None}

    placeholders = ", ".join(["%s"] * len(path_ids))

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT l.category_id, l.template_id, l.position, t.name, t.category_id, t.created_at, t.updated_at
                FROM category_template_links_tenant_rel l
                JOIN templates_tenant_rel t
                  ON t.organization_id = l.organization_id
                 AND t.id = l.template_id
                WHERE l.organization_id = %s
                  AND l.category_id IN ({placeholders})
                ORDER BY l.category_id, l.position, l.template_id
                """,
                [org_id, *path_ids],
            )
            link_rows = cur.fetchall() or []

        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for row in link_rows:
            category_id = str(row[0] or "").strip()
            template_id = str(row[1] or "").strip()
            if not category_id or not template_id:
                continue
            by_category.setdefault(category_id, []).append(
                {
                    "id": template_id,
                    "name": str(row[3] or template_id).strip() or template_id,
                    "category_id": str(row[4] or category_id).strip() or category_id,
                    "created_at": str(row[5] or "") or "",
                    "updated_at": str(row[6] or "") or "",
                }
            )

        owner_category_id = None
        template: Optional[Dict[str, Any]] = None
        for category_id in reversed(path_ids):
            items = by_category.get(category_id) or []
            if items:
                owner_category_id = category_id
                template = items[0]
                break

        if not template:
            return {"template": None, "attributes": [], "owner_category_id": None}

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT attr_id, name, code, attr_type, is_required,
                       scope, attribute_id, position, is_locked, options_json
                FROM template_attributes_tenant_rel
                WHERE organization_id = %s
                  AND template_id = %s
                ORDER BY position, code
                """,
                [org_id, template["id"]],
            )
            attr_rows = cur.fetchall() or []

        attributes: List[Dict[str, Any]] = []
        for row in attr_rows:
            options = row[9] if isinstance(row[9], dict) else {}
            if not isinstance(options, dict):
                try:
                    options = json.loads(str(row[9] or "{}"))
                except Exception:
                    options = {}
            attributes.append(
                {
                    "id": str(row[0] or "").strip(),
                    "name": str(row[1] or "").strip(),
                    "code": str(row[2] or "").strip(),
                    "type": str(row[3] or "text").strip() or "text",
                    "required": bool(row[4] or False),
                    "scope": str(row[5] or "common").strip() or "common",
                    "attribute_id": str(row[6] or "").strip() or None,
                    "position": int(row[7] or 0),
                    "locked": bool(row[8] or False),
                    "options": options if isinstance(options, dict) else {},
                }
            )

        return {
            "template": template,
            "attributes": attributes,
            "owner_category_id": owner_category_id,
        }

    return _with_pg_retry(_run)


def _normalize_products_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": []}
    items = doc.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: List[Dict[str, Any]] = []
    known_keys = {
        "id",
        "category_id",
        "type",
        "status",
        "title",
        "sku_pim",
        "sku_gt",
        "group_id",
        "selected_params",
        "feature_params",
        "exports_enabled",
        "content",
        "created_at",
        "updated_at",
    }
    for raw in items:
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "").strip()
        category_id = str(raw.get("category_id") or "").strip()
        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not pid or not category_id or not title:
            continue
        selected_params = raw.get("selected_params") if isinstance(raw.get("selected_params"), list) else []
        feature_params = raw.get("feature_params") if isinstance(raw.get("feature_params"), list) else []
        exports_enabled = raw.get("exports_enabled") if isinstance(raw.get("exports_enabled"), dict) else {}
        content = raw.get("content") if isinstance(raw.get("content"), dict) else {}
        extra = {k: v for k, v in raw.items() if k not in known_keys}
        normalized_items.append(
            {
                "id": pid,
                "category_id": category_id,
                "type": str(raw.get("type") or "single").strip() or "single",
                "status": str(raw.get("status") or "draft").strip() or "draft",
                "title": title,
                "sku_pim": str(raw.get("sku_pim") or "").strip(),
                "sku_gt": str(raw.get("sku_gt") or "").strip(),
                "group_id": str(raw.get("group_id") or "").strip() or None,
                "selected_params": [str(v).strip() for v in selected_params if str(v).strip()],
                "feature_params": [str(v).strip() for v in feature_params if str(v).strip()],
                "exports_enabled": exports_enabled,
                "content": content,
                "created_at": str(raw.get("created_at") or "").strip() or "",
                "updated_at": str(raw.get("updated_at") or "").strip() or "",
                "extra": extra if isinstance(extra, dict) else {},
            }
        )
    return {"version": 1, "items": normalized_items}


def _normalize_product_item(raw: Dict[str, Any]) -> Dict[str, Any] | None:
    normalized = _normalize_products_doc({"version": 1, "items": [raw]}).get("items", [])
    if not normalized:
        return None
    return normalized[0]


def _normalize_variant_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": []}
    items = doc.get("items")
    if not isinstance(items, list):
        items = []
    normalized_items: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        variant_id = str(raw.get("id") or "").strip()
        product_id = str(raw.get("product_id") or "").strip()
        if not variant_id or not product_id:
            continue
        normalized_items.append(
            {
                "id": variant_id,
                "product_id": product_id,
                "sku": str(raw.get("sku") or "").strip() or None,
                "sku_pim": str(raw.get("sku_pim") or "").strip() or None,
                "sku_gt": str(raw.get("sku_gt") or "").strip() or None,
                "title": str(raw.get("title") or "").strip() or None,
                "links": raw.get("links") if isinstance(raw.get("links"), list) else [],
                "content": raw.get("content") if isinstance(raw.get("content"), dict) else {},
                "options": raw.get("options") if isinstance(raw.get("options"), dict) else {},
                "status": str(raw.get("status") or "active").strip() or "active",
            }
        )
    return {"version": 1, "items": normalized_items}


def _preview_url_for_content(content: Dict[str, Any]) -> str:
    media_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
    media_legacy = content.get("media") if isinstance(content.get("media"), list) else []
    media_pool = media_images if media_images else media_legacy
    for media in media_pool:
        if isinstance(media, dict) and str(media.get("url") or "").strip():
            return str(media.get("url") or "").strip()
    return ""


def _replace_products_table(doc: Dict[str, Any]) -> None:
    normalized = _normalize_products_doc(doc)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    rows: List[tuple[Any, ...]] = []
    registry_rows: List[tuple[Any, ...]] = []
    counts: Dict[str, int] = {}
    for item in items:
        category_id = str(item.get("category_id") or "").strip()
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        preview_url = _preview_url_for_content(content)
        if category_id:
            counts[category_id] = int(counts.get(category_id, 0)) + 1
        rows.append(
            (
                str(item.get("id") or "").strip(),
                category_id,
                str(item.get("type") or "single").strip() or "single",
                str(item.get("status") or "draft").strip() or "draft",
                str(item.get("title") or "").strip(),
                str(item.get("sku_pim") or "").strip() or None,
                str(item.get("sku_gt") or "").strip() or None,
                str(item.get("group_id") or "").strip() or None,
                [str(v).strip() for v in (item.get("selected_params") or []) if str(v).strip()],
                [str(v).strip() for v in (item.get("feature_params") or []) if str(v).strip()],
                json.dumps(item.get("exports_enabled") if isinstance(item.get("exports_enabled"), dict) else {}),
                json.dumps(item.get("content") if isinstance(item.get("content"), dict) else {}),
                json.dumps(item.get("extra") if isinstance(item.get("extra"), dict) else {}),
                str(item.get("created_at") or "").strip() or None,
                str(item.get("updated_at") or "").strip() or None,
            )
        )
        registry_rows.append(
            (
                str(item.get("id") or "").strip(),
                str(item.get("title") or "").strip(),
                category_id,
                str(item.get("sku_pim") or "").strip() or None,
                str(item.get("sku_gt") or "").strip() or None,
                str(item.get("group_id") or "").strip() or None,
                preview_url or None,
                json.dumps(item.get("exports_enabled") if isinstance(item.get("exports_enabled"), dict) else {}),
                str(item.get("updated_at") or "").strip() or None,
            )
        )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products_rel")
            cur.execute("DELETE FROM catalog_product_registry_rel")
            cur.execute("DELETE FROM category_product_counts_rel")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO products_rel (
                      id, category_id, product_type, status, title, sku_pim, sku_gt, group_id,
                      selected_params, feature_params, exports_enabled_json, content_json, extra_json,
                      created_at, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s,
                      %s, %s, %s, %s, %s,
                      %s, %s
                    )
                    """,
                    rows,
                )
            if registry_rows:
                cur.executemany(
                    """
                    INSERT INTO catalog_product_registry_rel (
                      id, title, category_id, sku_pim, sku_gt, group_id, preview_url,
                      exports_enabled_json, updated_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s,
                      %s, %s
                    )
                    """,
                    registry_rows,
                )
            if counts:
                cur.executemany(
                    """
                    INSERT INTO category_product_counts_rel (
                      category_id, products_count, updated_at
                    ) VALUES (%s, %s, NOW())
                    """,
                    [(cid, count) for cid, count in counts.items()],
                )

    _with_pg_retry(_run)


def allocate_next_product_identity() -> Dict[str, str]:
    _ensure_tables()
    _bootstrap_products_from_legacy()

    def _run() -> Dict[str, str]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COALESCE(MAX(CASE WHEN id ~ '^product_[0-9]+$' THEN SUBSTRING(id FROM 9)::bigint END), 0),
                  COALESCE(MAX(CASE WHEN COALESCE(sku_pim, '') ~ '^[0-9]+$' THEN sku_pim::bigint END), 0),
                  COALESCE(MAX(CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN sku_gt::bigint END), 50000)
                FROM products_rel
                """
            )
            row = cur.fetchone() or [0, 0, 50000]
        return {
            "product_id": f"product_{int(row[0] or 0) + 1}",
            "next_sku_pim": str(int(row[1] or 0) + 1),
            "next_sku_gt": str(int(row[2] or 50000) + 1),
        }

    return _with_pg_retry(_run)


def _bootstrap_products_from_legacy() -> None:
    lock = with_lock("products_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("products_rel") > 0:
            return
        doc = read_doc(PRODUCTS_PATH, default={"version": 1, "items": []})
        if not isinstance(doc, dict):
            doc = {"version": 1, "items": []}
        _replace_products_table(doc)
    finally:
        lock.release()


def _replace_variants_table(doc: Dict[str, Any]) -> None:
    normalized = _normalize_variant_doc(doc)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    rows: List[tuple[Any, ...]] = []
    for item in items:
        rows.append(
            (
                str(item.get("id") or "").strip(),
                str(item.get("product_id") or "").strip(),
                str(item.get("sku") or "").strip() or None,
                str(item.get("sku_pim") or "").strip() or None,
                str(item.get("sku_gt") or "").strip() or None,
                str(item.get("title") or "").strip() or None,
                json.dumps(item.get("links") if isinstance(item.get("links"), list) else []),
                json.dumps(item.get("content") if isinstance(item.get("content"), dict) else {}),
                json.dumps(item.get("options") if isinstance(item.get("options"), dict) else {}),
                str(item.get("status") or "active").strip() or "active",
            )
        )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_variants_rel")
            if rows:
                cur.executemany(
                    """
                    INSERT INTO product_variants_rel (
                      id, product_id, sku, sku_pim, sku_gt, title,
                      links_json, content_json, options_json, status
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s,
                      %s::jsonb, %s::jsonb, %s::jsonb, %s
                    )
                    """,
                    rows,
                )

    _with_pg_retry(_run)


def _bootstrap_variants_from_legacy() -> None:
    lock = with_lock("product_variants_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("product_variants_rel") > 0:
            return
        doc = read_doc(VARIANTS_PATH, default={"version": 1, "items": []})
        if not isinstance(doc, dict):
            doc = {"version": 1, "items": []}
        _replace_variants_table(doc)
    finally:
        lock.release()


def save_templates_db_doc(doc: Dict[str, Any], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    normalized = _normalize_templates_doc(doc)
    _replace_templates_tenant_tables(normalized, organization_id)


def load_products_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_products_from_legacy()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id,
                  category_id,
                  product_type,
                  status,
                  title,
                  sku_pim,
                  sku_gt,
                  group_id,
                  selected_params,
                  feature_params,
                  exports_enabled_json,
                  content_json,
                  extra_json,
                  created_at,
                  updated_at
                FROM products_rel
                ORDER BY created_at NULLS LAST, id
                """
            )
            db_rows = cur.fetchall() or []

        items: List[Dict[str, Any]] = []
        for row in db_rows:
            exports_enabled = row[10] if isinstance(row[10], dict) else {}
            content = row[11] if isinstance(row[11], dict) else {}
            extra = row[12] if isinstance(row[12], dict) else {}
            item = {
                "id": str(row[0] or "").strip(),
                "category_id": str(row[1] or "").strip(),
                "type": str(row[2] or "single").strip() or "single",
                "status": str(row[3] or "draft").strip() or "draft",
                "title": str(row[4] or "").strip(),
                "sku_pim": str(row[5] or "").strip(),
                "sku_gt": str(row[6] or "").strip(),
                "selected_params": list(row[8] or []),
                "feature_params": list(row[9] or []),
                "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                "content": content if isinstance(content, dict) else {},
                "created_at": str(row[13] or "") or "",
                "updated_at": str(row[14] or "") or "",
            }
            group_id = str(row[7] or "").strip()
            if group_id:
                item["group_id"] = group_id
            if isinstance(extra, dict):
                for key, value in extra.items():
                    if key not in item:
                        item[key] = value
            items.append(item)
        return {"version": 1, "items": items}

    return _normalize_products_doc(_with_pg_retry(_run))


def load_products_by_ids(ids: List[str]) -> List[Dict[str, Any]]:
    return query_products_full(ids=ids)


def load_products_by_category(category_id: str) -> List[Dict[str, Any]]:
    cid = str(category_id or "").strip()
    if not cid:
        return []
    return query_products_full(category_ids=[cid])


def load_products_by_group(group_id: str) -> List[Dict[str, Any]]:
    gid = str(group_id or "").strip()
    if not gid:
        return []
    return query_products_full(group_ids=[gid])


def find_product_by_sku_gt(sku_gt: str) -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    needle = str(sku_gt or "").strip()
    if not needle:
        return {}

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, category_id, product_type, status, title, sku_pim, sku_gt, group_id,
                  selected_params, feature_params, exports_enabled_json, content_json, extra_json,
                  created_at, updated_at
                FROM products_rel
                WHERE sku_gt = %s
                LIMIT 1
                """,
                [needle],
            )
            row = cur.fetchone()
        if not row:
            return {}
        item = {
            "id": str(row[0] or "").strip(),
            "category_id": str(row[1] or "").strip(),
            "type": str(row[2] or "single").strip() or "single",
            "status": str(row[3] or "draft").strip() or "draft",
            "title": str(row[4] or "").strip(),
            "sku_pim": str(row[5] or "").strip(),
            "sku_gt": str(row[6] or "").strip(),
            "selected_params": list(row[8] or []),
            "feature_params": list(row[9] or []),
            "exports_enabled": row[10] if isinstance(row[10], dict) else {},
            "content": row[11] if isinstance(row[11], dict) else {},
            "created_at": str(row[13] or "") or "",
            "updated_at": str(row[14] or "") or "",
        }
        group_id = str(row[7] or "").strip()
        if group_id:
            item["group_id"] = group_id
        extra = row[12] if isinstance(row[12], dict) else {}
        for key, value in extra.items():
            if key not in item:
                item[key] = value
        return item

    return _with_pg_retry(_run)


def save_products_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    normalized = _normalize_products_doc(doc)
    _replace_products_table(normalized)


def _refresh_category_counts_for(category_ids: List[str]) -> None:
    safe_category_ids = [str(x or "").strip() for x in category_ids if str(x or "").strip()]
    if not safe_category_ids:
        return

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_product_counts_rel WHERE category_id = ANY(%s)", [safe_category_ids])
            cur.execute(
                """
                INSERT INTO category_product_counts_rel (category_id, products_count, updated_at)
                SELECT category_id, COUNT(*), NOW()
                FROM products_rel
                WHERE category_id = ANY(%s)
                GROUP BY category_id
                """,
                [safe_category_ids],
            )

    _with_pg_retry(_run)


def upsert_product_item(item: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    normalized = _normalize_product_item(item if isinstance(item, dict) else {})
    if not normalized:
        return {}
    category_id = str(normalized.get("category_id") or "").strip()
    content = normalized.get("content") if isinstance(normalized.get("content"), dict) else {}
    preview_url = _preview_url_for_content(content) or None
    exports_enabled = normalized.get("exports_enabled") if isinstance(normalized.get("exports_enabled"), dict) else {}
    extra = normalized.get("extra") if isinstance(normalized.get("extra"), dict) else {}
    product_id = str(normalized.get("id") or "").strip()

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT category_id FROM products_rel WHERE id = %s", [product_id])
            old_row = cur.fetchone()
            old_category_id = str((old_row or [None])[0] or "").strip()
            cur.execute(
                """
                INSERT INTO products_rel (
                  id, category_id, product_type, status, title, sku_pim, sku_gt, group_id,
                  selected_params, feature_params, exports_enabled_json, content_json, extra_json,
                  created_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                  %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                  category_id = EXCLUDED.category_id,
                  product_type = EXCLUDED.product_type,
                  status = EXCLUDED.status,
                  title = EXCLUDED.title,
                  sku_pim = EXCLUDED.sku_pim,
                  sku_gt = EXCLUDED.sku_gt,
                  group_id = EXCLUDED.group_id,
                  selected_params = EXCLUDED.selected_params,
                  feature_params = EXCLUDED.feature_params,
                  exports_enabled_json = EXCLUDED.exports_enabled_json,
                  content_json = EXCLUDED.content_json,
                  extra_json = EXCLUDED.extra_json,
                  created_at = COALESCE(products_rel.created_at, EXCLUDED.created_at),
                  updated_at = EXCLUDED.updated_at
                """,
                [
                    product_id,
                    category_id,
                    str(normalized.get("type") or "single").strip() or "single",
                    str(normalized.get("status") or "draft").strip() or "draft",
                    str(normalized.get("title") or "").strip(),
                    str(normalized.get("sku_pim") or "").strip() or None,
                    str(normalized.get("sku_gt") or "").strip() or None,
                    str(normalized.get("group_id") or "").strip() or None,
                    [str(v).strip() for v in (normalized.get("selected_params") or []) if str(v).strip()],
                    [str(v).strip() for v in (normalized.get("feature_params") or []) if str(v).strip()],
                    json.dumps(exports_enabled),
                    json.dumps(content),
                    json.dumps(extra),
                    str(normalized.get("created_at") or "").strip() or None,
                    str(normalized.get("updated_at") or "").strip() or None,
                ],
            )
            cur.execute(
                """
                INSERT INTO catalog_product_registry_rel (
                  id, title, category_id, sku_pim, sku_gt, group_id, preview_url, exports_enabled_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (id) DO UPDATE SET
                  title = EXCLUDED.title,
                  category_id = EXCLUDED.category_id,
                  sku_pim = EXCLUDED.sku_pim,
                  sku_gt = EXCLUDED.sku_gt,
                  group_id = EXCLUDED.group_id,
                  preview_url = EXCLUDED.preview_url,
                  exports_enabled_json = EXCLUDED.exports_enabled_json,
                  updated_at = EXCLUDED.updated_at
                """,
                [
                    product_id,
                    str(normalized.get("title") or "").strip(),
                    category_id,
                    str(normalized.get("sku_pim") or "").strip() or None,
                    str(normalized.get("sku_gt") or "").strip() or None,
                    str(normalized.get("group_id") or "").strip() or None,
                    preview_url,
                    json.dumps(exports_enabled),
                    str(normalized.get("updated_at") or "").strip() or None,
                ],
            )
            affected_categories = [category_id]
            if old_category_id and old_category_id != category_id:
                affected_categories.append(old_category_id)
        _refresh_category_counts_for(affected_categories)

    _with_pg_retry(_run)
    return normalized


def bulk_upsert_product_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    normalized_items = [
        normalized
        for normalized in (_normalize_product_item(item if isinstance(item, dict) else {}) for item in (items or []))
        if normalized
    ]
    if not normalized_items:
        return []

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        affected_categories: set[str] = set()
        with conn.cursor() as cur:
            product_ids = [str(item.get("id") or "").strip() for item in normalized_items if str(item.get("id") or "").strip()]
            old_category_map: Dict[str, str] = {}
            if product_ids:
                cur.execute("SELECT id, category_id FROM products_rel WHERE id = ANY(%s)", [product_ids])
                for row in cur.fetchall() or []:
                    pid = str(row[0] or "").strip()
                    cid = str(row[1] or "").strip()
                    if pid:
                        old_category_map[pid] = cid

            product_rows: List[List[Any]] = []
            registry_rows: List[List[Any]] = []
            for normalized in normalized_items:
                product_id = str(normalized.get("id") or "").strip()
                category_id = str(normalized.get("category_id") or "").strip()
                content = normalized.get("content") if isinstance(normalized.get("content"), dict) else {}
                preview_url = _preview_url_for_content(content) or None
                exports_enabled = normalized.get("exports_enabled") if isinstance(normalized.get("exports_enabled"), dict) else {}
                extra = normalized.get("extra") if isinstance(normalized.get("extra"), dict) else {}
                affected_categories.add(category_id)
                old_category_id = old_category_map.get(product_id, "")
                if old_category_id and old_category_id != category_id:
                    affected_categories.add(old_category_id)
                product_rows.append(
                    [
                        product_id,
                        category_id,
                        str(normalized.get("type") or "single").strip() or "single",
                        str(normalized.get("status") or "draft").strip() or "draft",
                        str(normalized.get("title") or "").strip(),
                        str(normalized.get("sku_pim") or "").strip() or None,
                        str(normalized.get("sku_gt") or "").strip() or None,
                        str(normalized.get("group_id") or "").strip() or None,
                        [str(v).strip() for v in (normalized.get("selected_params") or []) if str(v).strip()],
                        [str(v).strip() for v in (normalized.get("feature_params") or []) if str(v).strip()],
                        json.dumps(exports_enabled),
                        json.dumps(content),
                        json.dumps(extra),
                        str(normalized.get("created_at") or "").strip() or None,
                        str(normalized.get("updated_at") or "").strip() or None,
                    ]
                )
                registry_rows.append(
                    [
                        product_id,
                        str(normalized.get("title") or "").strip(),
                        category_id,
                        str(normalized.get("sku_pim") or "").strip() or None,
                        str(normalized.get("sku_gt") or "").strip() or None,
                        str(normalized.get("group_id") or "").strip() or None,
                        preview_url,
                        json.dumps(exports_enabled),
                        str(normalized.get("updated_at") or "").strip() or None,
                    ]
                )

            cur.executemany(
                """
                INSERT INTO products_rel (
                  id, category_id, product_type, status, title, sku_pim, sku_gt, group_id,
                  selected_params, feature_params, exports_enabled_json, content_json, extra_json,
                  created_at, updated_at
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                  %s, %s
                )
                ON CONFLICT (id) DO UPDATE SET
                  category_id = EXCLUDED.category_id,
                  product_type = EXCLUDED.product_type,
                  status = EXCLUDED.status,
                  title = EXCLUDED.title,
                  sku_pim = EXCLUDED.sku_pim,
                  sku_gt = EXCLUDED.sku_gt,
                  group_id = EXCLUDED.group_id,
                  selected_params = EXCLUDED.selected_params,
                  feature_params = EXCLUDED.feature_params,
                  exports_enabled_json = EXCLUDED.exports_enabled_json,
                  content_json = EXCLUDED.content_json,
                  extra_json = EXCLUDED.extra_json,
                  created_at = COALESCE(products_rel.created_at, EXCLUDED.created_at),
                  updated_at = EXCLUDED.updated_at
                """,
                product_rows,
            )
            cur.executemany(
                """
                INSERT INTO catalog_product_registry_rel (
                  id, title, category_id, sku_pim, sku_gt, group_id, preview_url, exports_enabled_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (id) DO UPDATE SET
                  title = EXCLUDED.title,
                  category_id = EXCLUDED.category_id,
                  sku_pim = EXCLUDED.sku_pim,
                  sku_gt = EXCLUDED.sku_gt,
                  group_id = EXCLUDED.group_id,
                  preview_url = EXCLUDED.preview_url,
                  exports_enabled_json = EXCLUDED.exports_enabled_json,
                  updated_at = EXCLUDED.updated_at
                """,
                registry_rows,
            )
        _refresh_category_counts_for(sorted(affected_categories))
        return normalized_items

    return _with_pg_retry(_run)


def allocate_next_variant_identity() -> str:
    _ensure_tables()
    _bootstrap_variants_from_legacy()

    def _run() -> str:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(CASE WHEN id ~ '^variant_[0-9]+$' THEN SUBSTRING(id FROM 9)::bigint END), 0)
                FROM product_variants_rel
                """
            )
            row = cur.fetchone() or [0]
        return f"variant_{int((row or [0])[0] or 0) + 1}"

    return str(_with_pg_retry(_run) or "variant_1")


def list_product_variants(product_id: str) -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_variants_from_legacy()
    pid = str(product_id or "").strip()
    if not pid:
        return []

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, product_id, sku, sku_pim, sku_gt, title, links_json, content_json, options_json, status
                FROM product_variants_rel
                WHERE product_id = %s
                ORDER BY id
                """,
                [pid],
            )
            rows = cur.fetchall() or []
        return [
            {
                "id": str(row[0] or "").strip(),
                "product_id": str(row[1] or "").strip(),
                "sku": str(row[2] or "").strip(),
                "sku_pim": str(row[3] or "").strip(),
                "sku_gt": str(row[4] or "").strip(),
                "title": str(row[5] or "").strip(),
                "links": row[6] if isinstance(row[6], list) else [],
                "content": row[7] if isinstance(row[7], dict) else {},
                "options": row[8] if isinstance(row[8], dict) else {},
                "status": str(row[9] or "active").strip() or "active",
            }
            for row in rows
        ]

    return _normalize_variant_doc({"version": 1, "items": _with_pg_retry(_run)}).get("items", [])


def find_product_variant(variant_id: str) -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_variants_from_legacy()
    vid = str(variant_id or "").strip()
    if not vid:
        return {}

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, product_id, sku, sku_pim, sku_gt, title, links_json, content_json, options_json, status
                FROM product_variants_rel
                WHERE id = %s
                LIMIT 1
                """,
                [vid],
            )
            row = cur.fetchone()
        if not row:
            return {}
        return {
            "id": str(row[0] or "").strip(),
            "product_id": str(row[1] or "").strip(),
            "sku": str(row[2] or "").strip(),
            "sku_pim": str(row[3] or "").strip(),
            "sku_gt": str(row[4] or "").strip(),
            "title": str(row[5] or "").strip(),
            "links": row[6] if isinstance(row[6], list) else [],
            "content": row[7] if isinstance(row[7], dict) else {},
            "options": row[8] if isinstance(row[8], dict) else {},
            "status": str(row[9] or "active").strip() or "active",
        }

    return _normalize_variant_doc({"version": 1, "items": [_with_pg_retry(_run)]}).get("items", [{}])[0]


def find_product_variant_by_sku(sku: str) -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_variants_from_legacy()
    needle = str(sku or "").strip()
    if not needle:
        return {}

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, product_id, sku, sku_pim, sku_gt, title, links_json, content_json, options_json, status
                FROM product_variants_rel
                WHERE sku = %s
                LIMIT 1
                """,
                [needle],
            )
            row = cur.fetchone()
        if not row:
            return {}
        return {
            "id": str(row[0] or "").strip(),
            "product_id": str(row[1] or "").strip(),
            "sku": str(row[2] or "").strip(),
            "sku_pim": str(row[3] or "").strip(),
            "sku_gt": str(row[4] or "").strip(),
            "title": str(row[5] or "").strip(),
            "links": row[6] if isinstance(row[6], list) else [],
            "content": row[7] if isinstance(row[7], dict) else {},
            "options": row[8] if isinstance(row[8], dict) else {},
            "status": str(row[9] or "active").strip() or "active",
        }

    return _normalize_variant_doc({"version": 1, "items": [_with_pg_retry(_run)]}).get("items", [{}])[0]


def insert_product_variants(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_variants_from_legacy()
    normalized_items = [
        item
        for item in (_normalize_variant_doc({"version": 1, "items": items}).get("items") or [])
        if isinstance(item, dict)
    ]
    if not normalized_items:
        return []

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO product_variants_rel (
                  id, product_id, sku, sku_pim, sku_gt, title,
                  links_json, content_json, options_json, status
                ) VALUES (
                  %s, %s, %s, %s, %s, %s,
                  %s::jsonb, %s::jsonb, %s::jsonb, %s
                )
                """,
                [
                    [
                        str(item.get("id") or "").strip(),
                        str(item.get("product_id") or "").strip(),
                        str(item.get("sku") or "").strip() or None,
                        str(item.get("sku_pim") or "").strip() or None,
                        str(item.get("sku_gt") or "").strip() or None,
                        str(item.get("title") or "").strip() or None,
                        json.dumps(item.get("links") if isinstance(item.get("links"), list) else []),
                        json.dumps(item.get("content") if isinstance(item.get("content"), dict) else {}),
                        json.dumps(item.get("options") if isinstance(item.get("options"), dict) else {}),
                        str(item.get("status") or "active").strip() or "active",
                    ]
                    for item in normalized_items
                ],
            )

    _with_pg_retry(_run)
    return normalized_items


def update_product_variant_sku(variant_id: str, sku: str) -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_variants_from_legacy()
    vid = str(variant_id or "").strip()
    next_sku = str(sku or "").strip() or None
    if not vid:
        return {}

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("UPDATE product_variants_rel SET sku = %s WHERE id = %s RETURNING id", [next_sku, vid])
            row = cur.fetchone()
        return {"id": str((row or [None])[0] or "").strip()}

    result = _with_pg_retry(_run)
    if not str(result.get("id") or "").strip():
        return {}
    return find_product_variant(vid)


def delete_product_items(ids: List[str]) -> int:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    safe_ids = [str(x or "").strip() for x in ids if str(x or "").strip()]
    if not safe_ids:
        return 0

    def _run() -> int:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT category_id FROM products_rel WHERE id = ANY(%s)", [safe_ids])
            category_rows = cur.fetchall() or []
            affected_categories = [str(row[0] or "").strip() for row in category_rows if str(row[0] or "").strip()]
            cur.execute("DELETE FROM catalog_product_registry_rel WHERE id = ANY(%s)", [safe_ids])
            cur.execute("DELETE FROM catalog_product_page_rel WHERE product_id = ANY(%s)", [safe_ids])
            cur.execute("DELETE FROM catalog_product_page_tenant_rel WHERE product_id = ANY(%s)", [safe_ids])
            cur.execute("DELETE FROM product_marketplace_status_rel WHERE product_id = ANY(%s)", [safe_ids])
            cur.execute("DELETE FROM product_marketplace_status_tenant_rel WHERE product_id = ANY(%s)", [safe_ids])
            cur.execute("DELETE FROM products_rel WHERE id = ANY(%s)", [safe_ids])
            deleted = int(cur.rowcount or 0)
        _refresh_category_counts_for(affected_categories)
        return deleted

    return _with_pg_retry(_run)


def load_catalog_product_items() -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_products_from_legacy()

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, category_id, sku_pim, sku_gt, group_id, preview_url, exports_enabled_json
                FROM catalog_product_registry_rel
                ORDER BY title, id
                """
            )
            rows = cur.fetchall() or []
        out: List[Dict[str, Any]] = []
        for row in rows:
            exports_enabled = row[7] if isinstance(row[7], dict) else {}
            out.append(
                {
                    "id": str(row[0] or "").strip(),
                    "name": str(row[1] or "").strip(),
                    "title": str(row[1] or "").strip(),
                    "category_id": str(row[2] or "").strip(),
                    "sku_pim": str(row[3] or "").strip(),
                    "sku_gt": str(row[4] or "").strip(),
                    "group_id": str(row[5] or "").strip(),
                    "preview_url": str(row[6] or "").strip(),
                    "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                }
            )
        return out

    return _with_pg_retry(_run)


def query_catalog_product_items(
    *,
    ids: List[str] | None = None,
    category_ids: List[str] | None = None,
    q: str = "",
    limit: int | None = None,
) -> List[Dict[str, Any]]:
    _ensure_tables()
    safe_ids = [str(x or "").strip() for x in (ids or []) if str(x or "").strip()]
    safe_category_ids = [str(x or "").strip() for x in (category_ids or []) if str(x or "").strip()]
    query = str(q or "").strip().lower()

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        sql = """
            SELECT id, title, category_id, sku_pim, sku_gt, group_id, preview_url, exports_enabled_json
            FROM catalog_product_registry_rel
        """
        clauses: List[str] = []
        params: List[Any] = []
        if safe_ids:
            clauses.append("id = ANY(%s)")
            params.append(safe_ids)
        if safe_category_ids:
            clauses.append("category_id = ANY(%s)")
            params.append(safe_category_ids)
        if query:
            clauses.append(
                "(LOWER(title) LIKE %s OR LOWER(COALESCE(sku_pim, '')) LIKE %s OR LOWER(COALESCE(sku_gt, '')) LIKE %s OR LOWER(id) LIKE %s)"
            )
            like = f"%{query}%"
            params.extend([like, like, like, like])
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN 0 ELSE 1 END, CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN LPAD(sku_gt, 32, '0') ELSE LOWER(COALESCE(sku_gt, '')) END, LOWER(title), id"
        if isinstance(limit, int) and limit > 0:
            sql += " LIMIT %s"
            params.append(int(limit))
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
        out: List[Dict[str, Any]] = []
        for row in rows:
            exports_enabled = row[7] if isinstance(row[7], dict) else {}
            out.append(
                {
                    "id": str(row[0] or "").strip(),
                    "name": str(row[1] or "").strip(),
                    "title": str(row[1] or "").strip(),
                    "category_id": str(row[2] or "").strip(),
                    "sku_pim": str(row[3] or "").strip(),
                    "sku_gt": str(row[4] or "").strip(),
                    "group_id": str(row[5] or "").strip(),
                    "preview_url": str(row[6] or "").strip(),
                    "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                }
            )
        return out

    return _with_pg_retry(_run)


def query_products_full(
    *,
    ids: List[str] | None = None,
    category_ids: List[str] | None = None,
    group_ids: List[str] | None = None,
) -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    safe_ids = [str(x or "").strip() for x in (ids or []) if str(x or "").strip()]
    safe_category_ids = [str(x or "").strip() for x in (category_ids or []) if str(x or "").strip()]
    safe_group_ids = [str(x or "").strip() for x in (group_ids or []) if str(x or "").strip()]

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        sql = """
            SELECT
              id, category_id, product_type, status, title, sku_pim, sku_gt, group_id,
              selected_params, feature_params, exports_enabled_json, content_json, extra_json,
              created_at, updated_at
            FROM products_rel
        """
        clauses: List[str] = []
        params: List[Any] = []
        if safe_ids:
            clauses.append("id = ANY(%s)")
            params.append(safe_ids)
        if safe_category_ids:
            clauses.append("category_id = ANY(%s)")
            params.append(safe_category_ids)
        if safe_group_ids:
            clauses.append("group_id = ANY(%s)")
            params.append(safe_group_ids)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at NULLS LAST, id"
        with conn.cursor() as cur:
            cur.execute(sql, params)
            db_rows = cur.fetchall() or []

        items: List[Dict[str, Any]] = []
        for row in db_rows:
            exports_enabled = row[10] if isinstance(row[10], dict) else {}
            content = row[11] if isinstance(row[11], dict) else {}
            extra = row[12] if isinstance(row[12], dict) else {}
            item = {
                "id": str(row[0] or "").strip(),
                "category_id": str(row[1] or "").strip(),
                "type": str(row[2] or "single").strip() or "single",
                "status": str(row[3] or "draft").strip() or "draft",
                "title": str(row[4] or "").strip(),
                "sku_pim": str(row[5] or "").strip(),
                "sku_gt": str(row[6] or "").strip(),
                "selected_params": list(row[8] or []),
                "feature_params": list(row[9] or []),
                "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                "content": content if isinstance(content, dict) else {},
                "created_at": str(row[13] or "") or "",
                "updated_at": str(row[14] or "") or "",
            }
            group_id = str(row[7] or "").strip()
            if group_id:
                item["group_id"] = group_id
            if isinstance(extra, dict):
                for key, value in extra.items():
                    if key not in item:
                        item[key] = value
            items.append(item)
        return items

    return _normalize_products_doc({"version": 1, "items": _with_pg_retry(_run)}).get("items", [])


def load_category_product_counts() -> Dict[str, int]:
    _ensure_tables()
    _bootstrap_products_from_legacy()

    def _run() -> Dict[str, int]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT category_id, products_count
                FROM category_product_counts_rel
                ORDER BY category_id
                """
            )
            rows = cur.fetchall() or []
        return {
            str(row[0] or "").strip(): int(row[1] or 0)
            for row in rows
            if str(row[0] or "").strip()
        }

    return _with_pg_retry(_run)


def load_products_count() -> int:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    return _table_count("products_rel")


def save_category_template_resolution(rows: List[Dict[str, Any]], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    deduped: Dict[str, tuple[str, str, Optional[str], Optional[str], Optional[str]]] = {}
    for row in rows or []:
        cid = str(row.get("category_id") or "").strip()
        if not cid:
            continue
        deduped[cid] = (
            org_id,
            cid,
            str(row.get("template_id") or "").strip() or None,
            str(row.get("template_name") or "").strip() or None,
            str(row.get("source_category_id") or "").strip() or None,
        )
    payload = list(deduped.values())

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_template_resolution_tenant_rel WHERE organization_id = %s", [org_id])
            if payload:
                cur.executemany(
                    """
                    INSERT INTO category_template_resolution_tenant_rel (
                      organization_id, category_id, template_id, template_name, source_category_id, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (organization_id, category_id) DO UPDATE SET
                      template_id = EXCLUDED.template_id,
                      template_name = EXCLUDED.template_name,
                      source_category_id = EXCLUDED.source_category_id,
                      updated_at = NOW()
                    """,
                    payload,
                )

    _with_pg_retry(_run)


def _bootstrap_category_template_resolution_tenant_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    lock = with_lock(f"category_template_resolution_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM category_template_resolution_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        if org_id == DEFAULT_ORGANIZATION_ID:
            def _legacy_rows() -> List[tuple[str, str, Optional[str], Optional[str], Optional[str]]]:
                conn, _, _ = _pg_connect()
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT category_id, template_id, template_name, source_category_id
                        FROM category_template_resolution_rel
                        ORDER BY category_id
                        """
                    )
                    rows = cur.fetchall() or []
                return [
                    (
                        org_id,
                        str(row[0] or "").strip(),
                        str(row[1] or "").strip() or None,
                        str(row[2] or "").strip() or None,
                        str(row[3] or "").strip() or None,
                    )
                    for row in rows
                    if str(row[0] or "").strip()
                ]

            payload = _with_pg_retry(_legacy_rows)
            if payload:
                def _insert() -> None:
                    conn, _, _ = _pg_connect()
                    with conn.cursor() as cur:
                        cur.executemany(
                            """
                            INSERT INTO category_template_resolution_tenant_rel (
                              organization_id, category_id, template_id, template_name, source_category_id, updated_at
                            ) VALUES (%s, %s, %s, %s, %s, NOW())
                            """,
                            payload,
                        )

                _with_pg_retry(_insert)
    finally:
        lock.release()


def load_category_template_resolution_map(organization_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_category_template_resolution_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Dict[str, str]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT category_id, template_id, template_name, source_category_id
                FROM category_template_resolution_tenant_rel
                WHERE organization_id = %s
                ORDER BY category_id
                """,
                [org_id],
            )
            rows = cur.fetchall() or []
        return {
            str(row[0] or "").strip(): {
                "template_id": str(row[1] or "").strip(),
                "template_name": str(row[2] or "").strip(),
                "source_category_id": str(row[3] or "").strip(),
            }
            for row in rows
            if str(row[0] or "").strip()
        }

    return _with_pg_retry(_run)


def save_product_marketplace_status(rows: List[Dict[str, Any]], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    _replace_product_marketplace_status_tenant_table(rows, organization_id)


def load_product_marketplace_status_map(organization_id: Optional[str] = None) -> Dict[str, Dict[str, Dict[str, Any]]]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_product_marketplace_status_tenant_from_legacy(org_id)

    def _run() -> Dict[str, Dict[str, Dict[str, Any]]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT product_id, yandex_present, yandex_status, ozon_present, ozon_status
                FROM product_marketplace_status_tenant_rel
                WHERE organization_id = %s
                ORDER BY product_id
                """,
                [org_id],
            )
            rows = cur.fetchall() or []
        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            pid = str(row[0] or "").strip()
            if not pid:
                continue
            out[pid] = {
                "yandex_market": {
                    "present": bool(row[1] or False),
                    "status": str(row[2] or "Нет данных").strip() or "Нет данных",
                },
                "ozon": {
                    "present": bool(row[3] or False),
                    "status": str(row[4] or "Нет данных").strip() or "Нет данных",
                },
            }
        return out

    return _with_pg_retry(_run)


def save_catalog_product_page_rows(rows: List[Dict[str, Any]], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    _replace_catalog_product_page_tenant_table(rows, organization_id)


def query_catalog_product_page_rows(
    *,
    category_ids: List[str] | None = None,
    exact_category_id: str = "",
    group_filter: str = "",
    template_filter: str = "",
    ym_filter: str = "all",
    oz_filter: str = "all",
    view_filter: str = "all",
    q: str = "",
    page: int = 1,
    page_size: int = 50,
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _resolve_organization_id(organization_id)
    _bootstrap_catalog_product_page_tenant_from_legacy(org_id)
    safe_category_ids = [str(x or "").strip() for x in (category_ids or []) if str(x or "").strip()]
    exact_category_id = str(exact_category_id or "").strip()
    group_filter = str(group_filter or "").strip()
    template_filter = str(template_filter or "").strip()
    ym_filter = str(ym_filter or "all").strip().lower()
    oz_filter = str(oz_filter or "all").strip().lower()
    view_filter = str(view_filter or "all").strip().lower()
    q = str(q or "").strip().lower()
    page = max(1, int(page or 1))
    page_size = max(1, min(int(page_size or 50), 200))

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        sql = """
            FROM catalog_product_page_tenant_rel
        """
        clauses: List[str] = ["organization_id = %s"]
        params: List[Any] = [org_id]
        if exact_category_id:
            clauses.append("category_id = %s")
            params.append(exact_category_id)
        elif safe_category_ids:
            clauses.append("category_id = ANY(%s)")
            params.append(safe_category_ids)

        if group_filter == "__ungrouped__":
            clauses.append("COALESCE(group_id, '') = ''")
        elif group_filter:
            clauses.append("group_id = %s")
            params.append(group_filter)

        if template_filter == "__without__":
            clauses.append("COALESCE(template_id, '') = ''")
        elif template_filter:
            clauses.append("template_id = %s")
            params.append(template_filter)

        if ym_filter == "on":
            clauses.append("yandex_present = TRUE")
        elif ym_filter == "off":
            clauses.append("yandex_present = FALSE")

        if oz_filter == "on":
            clauses.append("ozon_present = TRUE")
        elif oz_filter == "off":
            clauses.append("ozon_present = FALSE")

        if view_filter == "issues":
            clauses.append("(COALESCE(template_id, '') = '' OR yandex_present = FALSE OR ozon_present = FALSE)")
        elif view_filter == "no_template":
            clauses.append("COALESCE(template_id, '') = ''")
        elif view_filter == "no_ym":
            clauses.append("yandex_present = FALSE")
        elif view_filter == "no_oz":
            clauses.append("ozon_present = FALSE")
        elif view_filter == "no_photo":
            clauses.append("COALESCE(preview_url, '') = ''")
        elif view_filter == "no_group":
            clauses.append("COALESCE(group_id, '') = ''")

        if q:
            clauses.append(
                "(LOWER(title) LIKE %s OR LOWER(COALESCE(sku_gt, '')) LIKE %s OR LOWER(COALESCE(category_path, '')) LIKE %s)"
            )
            like = f"%{q}%"
            params.extend([like, like, like])

        where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql = " ORDER BY CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN 0 ELSE 1 END, CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN LPAD(sku_gt, 32, '0') ELSE LOWER(COALESCE(sku_gt, '')) END, LOWER(title), product_id"
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) {sql}{where_sql}", params)
            total_row = cur.fetchone()
            total = int((total_row or [0])[0] or 0)
            cur.execute(
                f"""
                SELECT
                  product_id, title, category_id, category_path, sku_pim, sku_gt, group_id, group_name,
                  template_id, template_name, template_source_category_id,
                  yandex_present, yandex_status, ozon_present, ozon_status,
                  preview_url, exports_enabled_json
                {sql}{where_sql}{order_sql}
                LIMIT %s OFFSET %s
                """,
                [*params, page_size, (page - 1) * page_size],
            )
            rows = cur.fetchall() or []
        items: List[Dict[str, Any]] = []
        for row in rows:
            exports_enabled = row[16] if isinstance(row[16], dict) else {}
            items.append(
                {
                    "id": str(row[0] or "").strip(),
                    "product_id": str(row[0] or "").strip(),
                    "title": str(row[1] or "").strip(),
                    "name": str(row[1] or "").strip(),
                    "category_id": str(row[2] or "").strip(),
                    "category_path": str(row[3] or "").strip(),
                    "sku_pim": str(row[4] or "").strip(),
                    "sku_gt": str(row[5] or "").strip(),
                    "group_id": str(row[6] or "").strip(),
                    "group_name": str(row[7] or "").strip(),
                    "effective_template_id": str(row[8] or "").strip(),
                    "effective_template_name": str(row[9] or "").strip(),
                    "effective_template_source_category_id": str(row[10] or "").strip(),
                    "marketplace_statuses": {
                        "yandex_market": {
                            "present": bool(row[11] or False),
                            "status": str(row[12] or "Нет данных").strip() or "Нет данных",
                        },
                        "ozon": {
                            "present": bool(row[13] or False),
                            "status": str(row[14] or "Нет данных").strip() or "Нет данных",
                        },
                    },
                    "preview_url": str(row[15] or "").strip(),
                    "exports_enabled": exports_enabled if isinstance(exports_enabled, dict) else {},
                }
            )
        return {"items": items, "total": total}

    return _with_pg_retry(_run)


def save_dashboard_stats_summary(payload: Dict[str, Any]) -> None:
    _ensure_tables()
    row = (
        "main",
        int(payload.get("categories") or 0),
        int(payload.get("products") or 0),
        int(payload.get("templates") or 0),
        int(payload.get("connectors_configured") or 0),
        int(payload.get("connectors_total") or 0),
    )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_stats_rel (
                  summary_key, categories_count, products_count, templates_count,
                  connectors_configured, connectors_total, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (summary_key) DO UPDATE SET
                  categories_count = EXCLUDED.categories_count,
                  products_count = EXCLUDED.products_count,
                  templates_count = EXCLUDED.templates_count,
                  connectors_configured = EXCLUDED.connectors_configured,
                  connectors_total = EXCLUDED.connectors_total,
                  updated_at = NOW()
                """,
                row,
            )

    _with_pg_retry(_run)


def load_dashboard_stats_summary() -> Dict[str, Any]:
    _ensure_tables()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT categories_count, products_count, templates_count,
                       connectors_configured, connectors_total, updated_at
                FROM dashboard_stats_rel
                WHERE summary_key = 'main'
                """
            )
            row = cur.fetchone()
        if not row:
            return {}
        return {
            "ok": True,
            "categories": int(row[0] or 0),
            "products": int(row[1] or 0),
            "templates": int(row[2] or 0),
            "connectors_configured": int(row[3] or 0),
            "connectors_total": int(row[4] or 0),
            "updated_at": row[5].isoformat() if row[5] else None,
        }

    return _with_pg_retry(_run)


def _normalize_product_groups_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    items = doc.get("items") if isinstance(doc, dict) else []
    out: List[Dict[str, Any]] = []
    for raw in items if isinstance(items, list) else []:
        if not isinstance(raw, dict):
            continue
        gid = str(raw.get("id") or "").strip()
        if not gid:
            continue
        seen: set[str] = set()
        variant_param_ids: List[str] = []
        for value in raw.get("variant_param_ids") if isinstance(raw.get("variant_param_ids"), list) else []:
            sid = str(value or "").strip()
            if not sid or sid in seen:
                continue
            seen.add(sid)
            variant_param_ids.append(sid)
        out.append(
            {
                "id": gid,
                "name": str(raw.get("name") or "").strip(),
                "variant_param_ids": variant_param_ids,
                "created_at": str(raw.get("created_at") or "").strip() or None,
                "updated_at": str(raw.get("updated_at") or "").strip() or None,
            }
        )
    out.sort(key=lambda row: (str(row.get("name") or "").lower(), str(row.get("id") or "")))
    return {"version": 1, "items": out}


def _replace_product_groups_table(doc: Dict[str, Any]) -> None:
    rows = _normalize_product_groups_doc(doc).get("items", [])
    group_rows = [
        (
            str(row.get("id") or "").strip(),
            str(row.get("name") or "").strip(),
            str(row.get("created_at") or "").strip() or None,
            str(row.get("updated_at") or "").strip() or None,
        )
        for row in rows
    ]
    variant_rows = []
    for row in rows:
        gid = str(row.get("id") or "").strip()
        for index, param_id in enumerate(row.get("variant_param_ids") or []):
            variant_rows.append((gid, str(param_id or "").strip(), index))

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_group_variant_params_rel")
            cur.execute("DELETE FROM product_groups_rel")
            if group_rows:
                cur.executemany(
                    """
                    INSERT INTO product_groups_rel (id, name, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    group_rows,
                )
            if variant_rows:
                cur.executemany(
                    """
                    INSERT INTO product_group_variant_params_rel (group_id, param_id, position)
                    VALUES (%s, %s, %s)
                    """,
                    variant_rows,
                )

    _with_pg_retry(_run)


def _bootstrap_product_groups_from_legacy() -> None:
    _ensure_tables()
    lock = with_lock("product_groups_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("product_groups_rel") > 0:
            return
        doc = read_doc(PRODUCT_GROUPS_PATH, default={"version": 1, "items": []})
        if not isinstance(doc, dict):
            doc = {"version": 1, "items": []}
        _replace_product_groups_table(doc)
    finally:
        lock.release()


def load_product_groups_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_product_groups_from_legacy()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT g.id, g.name, g.created_at, g.updated_at, vp.param_id
                FROM product_groups_rel g
                LEFT JOIN product_group_variant_params_rel vp
                  ON vp.group_id = g.id
                ORDER BY LOWER(g.name), g.id, vp.position, vp.param_id
                """
            )
            rows = cur.fetchall() or []
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            gid = str(row[0] or "").strip()
            if not gid:
                continue
            group = out.setdefault(
                gid,
                {
                    "id": gid,
                    "name": str(row[1] or "").strip(),
                    "variant_param_ids": [],
                    "created_at": str(row[2] or "").strip() or None,
                    "updated_at": str(row[3] or "").strip() or None,
                },
            )
            param_id = str(row[4] or "").strip()
            if param_id:
                group["variant_param_ids"].append(param_id)
        return {"version": 1, "items": list(out.values())}

    return _with_pg_retry(_run)


def save_product_groups_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    _replace_product_groups_table(doc if isinstance(doc, dict) else {"version": 1, "items": []})


def load_product_group_name_map() -> Dict[str, str]:
    _ensure_tables()
    _bootstrap_product_groups_from_legacy()

    def _run() -> Dict[str, str]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM product_groups_rel ORDER BY id")
            rows = cur.fetchall() or []
        return {
            str(row[0] or "").strip(): str(row[1] or "").strip()
            for row in rows
            if str(row[0] or "").strip()
        }

    return _with_pg_retry(_run)


def query_group_product_summaries(*, group_id: str = "", ungrouped_only: bool = False) -> List[Dict[str, Any]]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    group_id = str(group_id or "").strip()

    def _run() -> List[Dict[str, Any]]:
        conn, _, _ = _pg_connect()
        sql = """
            SELECT id, title, sku_pim, sku_gt, group_id, category_id
            FROM products_rel
        """
        clauses: List[str] = []
        params: List[Any] = []
        if group_id:
            clauses.append("group_id = %s")
            params.append(group_id)
        elif ungrouped_only:
            clauses.append("COALESCE(group_id, '') = ''")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN 0 ELSE 1 END, CASE WHEN COALESCE(sku_gt, '') ~ '^[0-9]+$' THEN LPAD(sku_gt, 32, '0') ELSE LOWER(COALESCE(sku_gt, '')) END, LOWER(title), id"
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() or []
        return [
            {
                "id": str(row[0] or "").strip(),
                "title": str(row[1] or "").strip(),
                "sku_pim": str(row[2] or "").strip(),
                "sku_gt": str(row[3] or "").strip(),
                "group_id": str(row[4] or "").strip(),
                "category_id": str(row[5] or "").strip(),
            }
            for row in rows
            if str(row[0] or "").strip()
        ]

    return _with_pg_retry(_run)


def load_group_category_counts() -> Dict[str, Dict[str, int]]:
    _ensure_tables()
    _bootstrap_products_from_legacy()

    def _run() -> Dict[str, Dict[str, int]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT group_id, category_id, COUNT(*)
                FROM products_rel
                WHERE COALESCE(group_id, '') <> ''
                GROUP BY group_id, category_id
                """
            )
            rows = cur.fetchall() or []
        out: Dict[str, Dict[str, int]] = {}
        for row in rows:
            gid = str(row[0] or "").strip()
            cid = str(row[1] or "").strip()
            if not gid or not cid:
                continue
            out.setdefault(gid, {})[cid] = int(row[2] or 0)
        return out

    return _with_pg_retry(_run)


def load_group_product_category_ids(group_id: str) -> List[str]:
    _ensure_tables()
    _bootstrap_products_from_legacy()
    group_id = str(group_id or "").strip()
    if not group_id:
        return []

    def _run() -> List[str]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT category_id
                FROM products_rel
                WHERE group_id = %s AND COALESCE(category_id, '') <> ''
                ORDER BY category_id
                """,
                [group_id],
            )
            rows = cur.fetchall() or []
        return [str(row[0] or "").strip() for row in rows if str(row[0] or "").strip()]

    return _with_pg_retry(_run)


def load_product_group_category_ids(group_id: str) -> List[str]:
    return load_group_product_category_ids(group_id)


def _default_connectors_state() -> Dict[str, Any]:
    return {"version": 1, "updated_at": None, "providers": {}}


def _collect_connectors_state_rows(doc: Dict[str, Any]) -> tuple[List[tuple[Any, ...]], List[tuple[Any, ...]], List[tuple[Any, ...]]]:
    providers = doc.get("providers") if isinstance(doc, dict) else {}
    method_rows: List[tuple[Any, ...]] = []
    settings_rows: List[tuple[Any, ...]] = []
    store_rows: List[tuple[Any, ...]] = []

    for provider, prow in providers.items() if isinstance(providers, dict) else []:
        pcode = str(provider or "").strip()
        if not pcode or not isinstance(prow, dict):
            continue
        methods = prow.get("methods") if isinstance(prow.get("methods"), dict) else {}
        settings = prow.get("settings") if isinstance(prow.get("settings"), dict) else {}
        import_stores = prow.get("import_stores") if isinstance(prow.get("import_stores"), list) else []

        for method, mrow in methods.items() if isinstance(methods, dict) else []:
            mcode = str(method or "").strip()
            if not mcode or not isinstance(mrow, dict):
                continue
            method_rows.append(
                (
                    pcode,
                    mcode,
                    str(mrow.get("schedule") or "").strip() or "1h",
                    str(mrow.get("last_run_at") or "").strip() or None,
                    str(mrow.get("last_success_at") or "").strip() or None,
                    str(mrow.get("last_error_at") or "").strip() or None,
                    str(mrow.get("last_error") or "").strip(),
                    int(mrow.get("fail_count") or 0),
                    str(mrow.get("status") or "ok").strip() or "ok",
                )
            )

        for key, value in settings.items() if isinstance(settings, dict) else []:
            skey = str(key or "").strip()
            if not skey:
                continue
            settings_rows.append((pcode, skey, str(value or "").strip()))

        for raw in import_stores:
            if not isinstance(raw, dict):
                continue
            store_id = str(raw.get("id") or "").strip()
            if not store_id:
                continue
            store_rows.append(
                (
                    pcode,
                    store_id,
                    str(raw.get("title") or "").strip(),
                    str(raw.get("business_id") or "").strip() or None,
                    str(raw.get("client_id") or "").strip() or None,
                    str(raw.get("api_key") or "").strip() or None,
                    str(raw.get("token") or "").strip() or None,
                    str(raw.get("auth_mode") or "").strip() or None,
                    bool(raw.get("enabled", True)),
                    str(raw.get("notes") or "").strip() or None,
                    str(raw.get("last_check_at") or "").strip() or None,
                    str(raw.get("last_check_status") or "").strip() or None,
                    str(raw.get("last_check_error") or "").strip() or None,
                    str(raw.get("created_at") or "").strip() or None,
                    str(raw.get("updated_at") or "").strip() or None,
                )
            )

    return method_rows, settings_rows, store_rows


def _replace_connectors_state_tables(doc: Dict[str, Any]) -> None:
    method_rows, settings_rows, store_rows = _collect_connectors_state_rows(doc)

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM connector_method_state_rel")
            cur.execute("DELETE FROM connector_provider_settings_rel")
            cur.execute("DELETE FROM connector_import_stores_rel")
            if method_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_method_state_rel (
                      provider, method, schedule, last_run_at, last_success_at, last_error_at,
                      last_error, fail_count, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    method_rows,
                )
            if settings_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_provider_settings_rel (
                      provider, setting_key, setting_value
                    ) VALUES (%s, %s, %s)
                    """,
                    settings_rows,
                )
            if store_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_import_stores_rel (
                      provider, store_id, title, business_id, client_id, api_key, token, auth_mode,
                      enabled, notes, last_check_at, last_check_status, last_check_error, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    store_rows,
                )

    _with_pg_retry(_run)


def _replace_connectors_state_tenant_tables(doc: Dict[str, Any], organization_id: Optional[str]) -> None:
    org_id = _normalize_organization_id(organization_id)
    method_rows, settings_rows, store_rows = _collect_connectors_state_rows(doc)

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM connector_method_state_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM connector_provider_settings_tenant_rel WHERE organization_id = %s", [org_id])
            cur.execute("DELETE FROM connector_import_stores_tenant_rel WHERE organization_id = %s", [org_id])
            if method_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_method_state_tenant_rel (
                      organization_id, provider, method, schedule, last_run_at, last_success_at, last_error_at,
                      last_error, fail_count, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [(org_id, *row) for row in method_rows],
                )
            if settings_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_provider_settings_tenant_rel (
                      organization_id, provider, setting_key, setting_value
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    [(org_id, *row) for row in settings_rows],
                )
            if store_rows:
                cur.executemany(
                    """
                    INSERT INTO connector_import_stores_tenant_rel (
                      organization_id, provider, store_id, title, business_id, client_id, api_key, token, auth_mode,
                      enabled, notes, last_check_at, last_check_status, last_check_error, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [(org_id, *row) for row in store_rows],
                )

    _with_pg_retry(_run)


def _bootstrap_connectors_state_from_legacy() -> None:
    _ensure_tables()
    lock = with_lock("connectors_state_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("connector_method_state_rel") > 0:
            return
        doc = read_doc(CONNECTORS_STATE_PATH, default=_default_connectors_state())
        if not isinstance(doc, dict):
            doc = _default_connectors_state()
        _replace_connectors_state_tables(doc)
    finally:
        lock.release()


def _bootstrap_tenant_connectors_state_from_legacy(organization_id: Optional[str]) -> None:
    _ensure_tables()
    org_id = _normalize_organization_id(organization_id)
    lock = with_lock(f"connectors_state_tenant_rel_bootstrap:{org_id}")
    lock.acquire()
    try:
        def _count() -> int:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM connector_method_state_tenant_rel WHERE organization_id = %s",
                    [org_id],
                )
                row = cur.fetchone()
                return int((row or [0])[0] or 0)

        if _with_pg_retry(_count) > 0:
            return
        _bootstrap_connectors_state_from_legacy()
        if org_id == DEFAULT_ORGANIZATION_ID:
            legacy_doc = load_connectors_state_doc_legacy()
            _replace_connectors_state_tenant_tables(legacy_doc, org_id)
    finally:
        lock.release()


def load_connectors_state_doc_legacy() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_connectors_state_from_legacy()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, method, schedule, last_run_at, last_success_at, last_error_at, last_error, fail_count, status
                FROM connector_method_state_rel
                ORDER BY provider, method
                """
            )
            method_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT provider, setting_key, setting_value
                FROM connector_provider_settings_rel
                ORDER BY provider, setting_key
                """
            )
            setting_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT provider, store_id, title, business_id, client_id, api_key, token, auth_mode,
                       enabled, notes, last_check_at, last_check_status, last_check_error, created_at, updated_at
                FROM connector_import_stores_rel
                ORDER BY provider, title, store_id
                """
            )
            store_rows = cur.fetchall() or []

        providers: Dict[str, Any] = {}
        for row in method_rows:
            provider = str(row[0] or "").strip()
            method = str(row[1] or "").strip()
            if not provider or not method:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["methods"][method] = {
                "schedule": str(row[2] or "").strip() or "1h",
                "last_run_at": str(row[3] or "").strip() or None,
                "last_success_at": str(row[4] or "").strip() or None,
                "last_error_at": str(row[5] or "").strip() or None,
                "last_error": str(row[6] or "").strip(),
                "fail_count": int(row[7] or 0),
                "status": str(row[8] or "").strip() or "ok",
            }

        for row in setting_rows:
            provider = str(row[0] or "").strip()
            key = str(row[1] or "").strip()
            if not provider or not key:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["settings"][key] = str(row[2] or "").strip()

        for row in store_rows:
            provider = str(row[0] or "").strip()
            if not provider:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["import_stores"].append(
                {
                    "id": str(row[1] or "").strip(),
                    "title": str(row[2] or "").strip(),
                    "business_id": str(row[3] or "").strip(),
                    "client_id": str(row[4] or "").strip(),
                    "api_key": str(row[5] or "").strip(),
                    "token": str(row[6] or "").strip(),
                    "auth_mode": str(row[7] or "").strip(),
                    "enabled": bool(row[8]),
                    "notes": str(row[9] or "").strip(),
                    "last_check_at": str(row[10] or "").strip() or None,
                    "last_check_status": str(row[11] or "").strip(),
                    "last_check_error": str(row[12] or "").strip(),
                    "created_at": str(row[13] or "").strip() or None,
                    "updated_at": str(row[14] or "").strip() or None,
                }
            )

        return {"version": 1, "updated_at": None, "providers": providers}

    return _with_pg_retry(_run)


def load_connectors_state_doc(organization_id: Optional[str] = None) -> Dict[str, Any]:
    _ensure_tables()
    org_id = _normalize_organization_id(organization_id)
    _bootstrap_tenant_connectors_state_from_legacy(org_id)

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider, method, schedule, last_run_at, last_success_at, last_error_at, last_error, fail_count, status
                FROM connector_method_state_tenant_rel
                WHERE organization_id = %s
                ORDER BY provider, method
                """,
                [org_id],
            )
            method_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT provider, setting_key, setting_value
                FROM connector_provider_settings_tenant_rel
                WHERE organization_id = %s
                ORDER BY provider, setting_key
                """,
                [org_id],
            )
            setting_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT provider, store_id, title, business_id, client_id, api_key, token, auth_mode,
                       enabled, notes, last_check_at, last_check_status, last_check_error, created_at, updated_at
                FROM connector_import_stores_tenant_rel
                WHERE organization_id = %s
                ORDER BY provider, title, store_id
                """,
                [org_id],
            )
            store_rows = cur.fetchall() or []

        providers: Dict[str, Any] = {}
        for row in method_rows:
            provider = str(row[0] or "").strip()
            method = str(row[1] or "").strip()
            if not provider or not method:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["methods"][method] = {
                "schedule": str(row[2] or "").strip() or "1h",
                "last_run_at": str(row[3] or "").strip() or None,
                "last_success_at": str(row[4] or "").strip() or None,
                "last_error_at": str(row[5] or "").strip() or None,
                "last_error": str(row[6] or "").strip(),
                "fail_count": int(row[7] or 0),
                "status": str(row[8] or "").strip() or "ok",
            }

        for row in setting_rows:
            provider = str(row[0] or "").strip()
            key = str(row[1] or "").strip()
            if not provider or not key:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["settings"][key] = str(row[2] or "").strip()

        for row in store_rows:
            provider = str(row[0] or "").strip()
            if not provider:
                continue
            prow = providers.setdefault(provider, {"methods": {}, "settings": {}, "import_stores": []})
            prow["import_stores"].append(
                {
                    "id": str(row[1] or "").strip(),
                    "title": str(row[2] or "").strip(),
                    "business_id": str(row[3] or "").strip(),
                    "client_id": str(row[4] or "").strip(),
                    "api_key": str(row[5] or "").strip(),
                    "token": str(row[6] or "").strip(),
                    "auth_mode": str(row[7] or "").strip(),
                    "enabled": bool(row[8]),
                    "notes": str(row[9] or "").strip(),
                    "last_check_at": str(row[10] or "").strip() or None,
                    "last_check_status": str(row[11] or "").strip(),
                    "last_check_error": str(row[12] or "").strip(),
                    "created_at": str(row[13] or "").strip() or None,
                    "updated_at": str(row[14] or "").strip() or None,
                }
            )

        return {"version": 1, "updated_at": None, "providers": providers}

    return _with_pg_retry(_run)


def save_connectors_state_doc(doc: Dict[str, Any], organization_id: Optional[str] = None) -> None:
    _ensure_tables()
    _replace_connectors_state_tenant_tables(
        doc if isinstance(doc, dict) else _default_connectors_state(),
        organization_id,
    )
