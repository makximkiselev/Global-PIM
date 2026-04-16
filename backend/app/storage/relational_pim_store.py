from __future__ import annotations

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
    write_doc(CATALOG_NODES_PATH, nodes)


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
    write_doc(CATEGORY_MAPPINGS_PATH, {"version": 1, "items": items})


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
    write_doc(ATTRIBUTE_MAPPINGS_PATH, doc)


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
    write_doc(ATTRIBUTE_VALUE_DICTIONARY_PATH, doc)
