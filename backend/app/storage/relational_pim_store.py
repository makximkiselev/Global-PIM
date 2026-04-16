from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

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


def _with_pg_retry(fn):
    try:
        return fn()
    except Exception as exc:
        if not _is_retryable_pg_error(exc):
            raise
        _reset_pg_connection()
        return fn()


def _ensure_tables() -> None:
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
                CREATE INDEX IF NOT EXISTS idx_category_mappings_rel_provider
                  ON category_mappings_rel(provider, provider_category_id)
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
                CREATE INDEX IF NOT EXISTS idx_attribute_mappings_rel_category
                  ON attribute_mappings_rel(catalog_category_id, catalog_name)
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
                CREATE INDEX IF NOT EXISTS idx_attribute_value_refs_rel_category
                  ON attribute_value_refs_rel(catalog_category_id, catalog_name)
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
                CREATE INDEX IF NOT EXISTS idx_dictionaries_rel_code
                  ON dictionaries_rel(code)
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
                CREATE INDEX IF NOT EXISTS idx_dictionary_values_rel_dict_position
                  ON dictionary_values_rel(dict_id, position, value_text)
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
                CREATE INDEX IF NOT EXISTS idx_templates_rel_category
                  ON templates_rel(category_id)
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
                CREATE INDEX IF NOT EXISTS idx_template_attributes_rel_template_position
                  ON template_attributes_rel(template_id, position, code)
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
                CREATE INDEX IF NOT EXISTS idx_category_template_links_rel_category_position
                  ON category_template_links_rel(category_id, position)
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

    _with_pg_retry(_run)


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


def _bootstrap_catalog_nodes_from_legacy() -> None:
    lock = with_lock("catalog_nodes_rel_bootstrap")
    lock.acquire()
    try:
        if _table_count("catalog_nodes_rel") > 0:
            return
        doc = read_doc(CATALOG_NODES_PATH, default=[])
        nodes = doc if isinstance(doc, list) else []
        _replace_catalog_nodes_table(nodes)
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


def load_category_mappings() -> Dict[str, Dict[str, str]]:
    _ensure_tables()
    _bootstrap_category_mappings_from_legacy()

    def _run() -> Dict[str, Dict[str, str]]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT catalog_category_id, provider, provider_category_id
                FROM category_mappings_rel
                ORDER BY catalog_category_id, provider
                """
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


def save_category_mappings(items: Dict[str, Dict[str, str]]) -> None:
    _ensure_tables()
    _replace_category_mappings_table(items)


def load_attribute_mapping_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_attribute_mappings_from_legacy()

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
                FROM attribute_mappings_rel
                ORDER BY catalog_category_id, catalog_name, row_id
                """
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


def save_attribute_mapping_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}}
    _replace_attribute_mappings_table(doc)


def load_attribute_value_refs_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_attribute_value_refs_from_legacy()

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
                FROM attribute_value_refs_rel
                ORDER BY catalog_category_id, catalog_name
                """
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


def save_attribute_value_refs_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    if not isinstance(doc, dict):
        doc = {"version": 2, "updated_at": None, "items": {}}
    _replace_attribute_value_refs_table(doc)


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
    out_items: List[Dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        did = _normalize_text(raw.get("id"))
        if not did:
            continue
        title = _normalize_text(raw.get("title")) or did
        code = _normalize_text(raw.get("code")) or (did[len("dict_"):] if did.startswith("dict_") else _slugify_code(title))
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        out_items.append(
            {
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
        )
    return {"version": 2, "items": out_items}


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


def load_dictionaries_db_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_dictionaries_from_legacy()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id, title, code, attr_id, attr_type, scope,
                  is_service, is_required, param_group, template_layer, created_at, updated_at
                FROM dictionaries_rel
                ORDER BY LOWER(title), id
                """
            )
            dict_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, value_key, value_text, value_count, last_seen, position
                FROM dictionary_values_rel
                ORDER BY dict_id, position, value_text
                """
            )
            value_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, value_key, source_name, source_count
                FROM dictionary_value_sources_rel
                ORDER BY dict_id, value_key, source_name
                """
            )
            source_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, alias_key, canonical_value
                FROM dictionary_aliases_rel
                ORDER BY dict_id, alias_key
                """
            )
            alias_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, provider, provider_param_id, provider_param_name, kind, is_required, allowed_values
                FROM dictionary_provider_refs_rel
                ORDER BY dict_id, provider
                """
            )
            provider_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT dict_id, provider, canonical_key, provider_value
                FROM dictionary_export_maps_rel
                ORDER BY dict_id, provider, canonical_key
                """
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


def save_dictionaries_db_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    normalized = _normalize_dictionary_doc(doc)
    _replace_dictionaries_tables(normalized)


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


def load_templates_db_doc() -> Dict[str, Any]:
    _ensure_tables()
    _bootstrap_templates_from_legacy()

    def _run() -> Dict[str, Any]:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, category_id, created_at, updated_at
                FROM templates_rel
                ORDER BY id
                """
            )
            template_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT template_id, attr_id, name, code, attr_type, is_required,
                       scope, attribute_id, position, is_locked, options_json
                FROM template_attributes_rel
                ORDER BY template_id, position, code
                """
            )
            attr_rows = cur.fetchall() or []
            cur.execute(
                """
                SELECT category_id, template_id, position
                FROM category_template_links_rel
                ORDER BY category_id, position, template_id
                """
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


def _replace_products_table(doc: Dict[str, Any]) -> None:
    normalized = _normalize_products_doc(doc)
    items = normalized.get("items") if isinstance(normalized.get("items"), list) else []
    rows: List[tuple[Any, ...]] = []
    registry_rows: List[tuple[Any, ...]] = []
    counts: Dict[str, int] = {}
    for item in items:
        category_id = str(item.get("category_id") or "").strip()
        content = item.get("content") if isinstance(item.get("content"), dict) else {}
        media_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        media_legacy = content.get("media") if isinstance(content.get("media"), list) else []
        media_pool = media_images if media_images else media_legacy
        preview_url = ""
        for media in media_pool:
            if isinstance(media, dict) and str(media.get("url") or "").strip():
                preview_url = str(media.get("url") or "").strip()
                break
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


def save_templates_db_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    normalized = _normalize_templates_doc(doc)
    _replace_templates_tables(normalized)


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


def save_products_doc(doc: Dict[str, Any]) -> None:
    _ensure_tables()
    normalized = _normalize_products_doc(doc)
    _replace_products_table(normalized)


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


def save_category_template_resolution(rows: List[Dict[str, Any]]) -> None:
    _ensure_tables()
    payload = []
    for row in rows or []:
        cid = str(row.get("category_id") or "").strip()
        if not cid:
            continue
        payload.append(
            (
                cid,
                str(row.get("template_id") or "").strip() or None,
                str(row.get("template_name") or "").strip() or None,
                str(row.get("source_category_id") or "").strip() or None,
            )
        )

    def _run() -> None:
        conn, _, _ = _pg_connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM category_template_resolution_rel")
            if payload:
                cur.executemany(
                    """
                    INSERT INTO category_template_resolution_rel (
                      category_id, template_id, template_name, source_category_id, updated_at
                    ) VALUES (%s, %s, %s, %s, NOW())
                    """,
                    payload,
                )

    _with_pg_retry(_run)


def load_category_template_resolution_map() -> Dict[str, Dict[str, str]]:
    _ensure_tables()

    def _run() -> Dict[str, Dict[str, str]]:
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


def save_product_marketplace_status(rows: List[Dict[str, Any]]) -> None:
    _ensure_tables()
    payload = []
    for row in rows or []:
        pid = str(row.get("product_id") or "").strip()
        if not pid:
            continue
        payload.append(
            (
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
            cur.execute("DELETE FROM product_marketplace_status_rel")
            if payload:
                cur.executemany(
                    """
                    INSERT INTO product_marketplace_status_rel (
                      product_id, yandex_present, yandex_status, ozon_present, ozon_status, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    payload,
                )

    _with_pg_retry(_run)


def load_product_marketplace_status_map() -> Dict[str, Dict[str, Dict[str, Any]]]:
    _ensure_tables()

    def _run() -> Dict[str, Dict[str, Dict[str, Any]]]:
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
