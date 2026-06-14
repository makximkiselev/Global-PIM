#!/usr/bin/env python3
from __future__ import annotations

import gzip
import json
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - depends on server runtime
    psycopg = None

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - depends on server runtime
    psycopg2 = None


APP_DIR = Path(os.getenv("APP_DIR", "/opt/projects/global-pim"))
ENV_FILE = Path(os.getenv("APP_ENV_FILE", str(APP_DIR / "backend" / ".env")))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(APP_DIR / "backups")))
DEFAULT_ORG_ID = os.getenv("DEFAULT_ORG_ID", "org_global_trade").strip() or "org_global_trade"


def env_value(key: str) -> str:
    if os.getenv(key):
        return str(os.getenv(key) or "").strip()
    if not ENV_FILE.exists():
        return ""
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    return str(value)


def connect(dsn: str) -> Any:
    if psycopg is not None:
        return psycopg.connect(dsn)
    if psycopg2 is not None:
        return psycopg2.connect(dsn)
    raise RuntimeError("psycopg or psycopg2 is required")


def fetch_rows(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    columns = [getattr(desc, "name", None) or desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def table_exists(cur: Any, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
    return bool((cur.fetchone() or [None])[0])


def backup_touched_rows(cur: Any, organization_id: str, backup_path: Path) -> dict[str, int]:
    queries: dict[str, tuple[str, tuple[Any, ...]]] = {
        "connector_import_stores_tenant_rel": (
            "SELECT * FROM connector_import_stores_tenant_rel WHERE organization_id = %s AND provider = 'ozon'",
            (organization_id,),
        ),
        "connector_method_state_tenant_rel": (
            "SELECT * FROM connector_method_state_tenant_rel WHERE organization_id = %s AND provider = 'ozon'",
            (organization_id,),
        ),
        "connector_provider_settings_tenant_rel": (
            "SELECT * FROM connector_provider_settings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'",
            (organization_id,),
        ),
        "category_mappings_tenant_rel": (
            "SELECT * FROM category_mappings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'",
            (organization_id,),
        ),
        "attribute_provider_bindings_tenant_rel": (
            "SELECT * FROM attribute_provider_bindings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'",
            (organization_id,),
        ),
        "attribute_mappings_tenant_rel": (
            """
            SELECT * FROM attribute_mappings_tenant_rel
            WHERE organization_id = %s
              AND (
                COALESCE(ozon_param_id, '') <> ''
                OR COALESCE(ozon_param_name, '') <> ''
                OR ozon_bindings_json IS NOT NULL
                OR ozon_required
                OR ozon_export
              )
            """,
            (organization_id,),
        ),
        "attribute_value_refs_tenant_rel": (
            """
            SELECT * FROM attribute_value_refs_tenant_rel
            WHERE organization_id = %s
              AND (
                COALESCE(ozon_provider_category_id, '') <> ''
                OR COALESCE(ozon_param_id, '') <> ''
                OR COALESCE(ozon_param_name, '') <> ''
                OR ozon_required
                OR ozon_export
              )
            """,
            (organization_id,),
        ),
        "templates_tenant_rel": (
            """
            SELECT * FROM templates_tenant_rel
            WHERE organization_id = %s
              AND (
                meta_json ? 'sources'
                OR meta_json::text ILIKE '%%ozon%%'
              )
            """,
            (organization_id,),
        ),
        "products_rel": (
            """
            SELECT * FROM products_rel
            WHERE exports_enabled_json ? 'ozon'
               OR (content_json ? 'source_values' AND content_json->'source_values' ? 'ozon')
               OR (content_json ? 'source_meta' AND content_json->'source_meta' ? 'ozon')
            """,
            (),
        ),
        "product_marketplace_status_tenant_rel": (
            """
            SELECT * FROM product_marketplace_status_tenant_rel
            WHERE organization_id = %s AND (ozon_present OR ozon_status <> 'Нет данных')
            """,
            (organization_id,),
        ),
        "catalog_product_page_tenant_rel": (
            """
            SELECT * FROM catalog_product_page_tenant_rel
            WHERE organization_id = %s AND (ozon_present OR ozon_status <> 'Нет данных')
            """,
            (organization_id,),
        ),
        "json_documents": (
            """
            SELECT * FROM json_documents
            WHERE path LIKE 'marketplaces/ozon/%%'
               OR path IN (
                 'marketplaces/ozon/category_attributes.json',
                 'marketplaces/ozon/categories_tree.json',
                 'marketplaces/ozon/import_products_info.json',
                 'marketplaces/ozon/product_rating_by_sku.json'
               )
            """,
            (),
        ),
    }
    payload: dict[str, Any] = {"organization_id": organization_id, "created_at": datetime.now().isoformat(), "tables": {}}
    counts: dict[str, int] = {}
    for table, (sql, params) in queries.items():
        if not table_exists(cur, table):
            payload["tables"][table] = []
            counts[table] = 0
            continue
        rows = fetch_rows(cur, sql, params)
        payload["tables"][table] = rows
        counts[table] = len(rows)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(backup_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=json_default)
    return counts


def cleanup_ozon(cur: Any, organization_id: str) -> dict[str, int]:
    statements: list[tuple[str, str, tuple[Any, ...]]] = [
        ("connector_import_stores_tenant_rel", "DELETE FROM connector_import_stores_tenant_rel WHERE organization_id = %s AND provider = 'ozon'", (organization_id,)),
        ("connector_method_state_tenant_rel", "DELETE FROM connector_method_state_tenant_rel WHERE organization_id = %s AND provider = 'ozon'", (organization_id,)),
        ("connector_provider_settings_tenant_rel", "DELETE FROM connector_provider_settings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'", (organization_id,)),
        ("category_mappings_tenant_rel", "DELETE FROM category_mappings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'", (organization_id,)),
        ("attribute_provider_bindings_tenant_rel", "DELETE FROM attribute_provider_bindings_tenant_rel WHERE organization_id = %s AND provider = 'ozon'", (organization_id,)),
        (
            "attribute_mappings_tenant_rel",
            """
            UPDATE attribute_mappings_tenant_rel
            SET ozon_param_id = NULL,
                ozon_param_name = NULL,
                ozon_kind = NULL,
                ozon_values = NULL,
                ozon_required = FALSE,
                ozon_export = FALSE,
                ozon_bindings_json = NULL,
                updated_at = NOW()
            WHERE organization_id = %s
              AND (
                COALESCE(ozon_param_id, '') <> ''
                OR COALESCE(ozon_param_name, '') <> ''
                OR ozon_bindings_json IS NOT NULL
                OR ozon_required
                OR ozon_export
              )
            """,
            (organization_id,),
        ),
        (
            "attribute_value_refs_tenant_rel",
            """
            UPDATE attribute_value_refs_tenant_rel
            SET ozon_provider_category_id = NULL,
                ozon_param_id = NULL,
                ozon_param_name = NULL,
                ozon_kind = NULL,
                ozon_allowed_values = NULL,
                ozon_required = FALSE,
                ozon_export = FALSE,
                updated_at = NOW()
            WHERE organization_id = %s
              AND (
                COALESCE(ozon_provider_category_id, '') <> ''
                OR COALESCE(ozon_param_id, '') <> ''
                OR COALESCE(ozon_param_name, '') <> ''
                OR ozon_required
                OR ozon_export
              )
            """,
            (organization_id,),
        ),
        (
            "templates_tenant_rel",
            """
            UPDATE templates_tenant_rel
            SET meta_json =
              CASE
                WHEN meta_json ? 'sources' THEN jsonb_set(meta_json, '{sources}', COALESCE(meta_json->'sources', '{}'::jsonb) - 'ozon', true)
                ELSE meta_json
              END,
              updated_at = NOW()::text
            WHERE organization_id = %s
              AND meta_json ? 'sources'
              AND meta_json->'sources' ? 'ozon'
            """,
            (organization_id,),
        ),
        (
            "products_rel",
            """
            UPDATE products_rel
            SET exports_enabled_json = COALESCE(exports_enabled_json, '{}'::jsonb) - 'ozon',
                content_json = jsonb_set(
                    jsonb_set(
                      content_json,
                      '{source_values}',
                      COALESCE(content_json->'source_values', '{}'::jsonb) - 'ozon',
                      true
                    ),
                    '{source_meta}',
                    COALESCE(content_json->'source_meta', '{}'::jsonb) - 'ozon',
                    true
                  ),
                updated_at = NOW()::text
            WHERE exports_enabled_json ? 'ozon'
               OR (content_json ? 'source_values' AND content_json->'source_values' ? 'ozon')
               OR (content_json ? 'source_meta' AND content_json->'source_meta' ? 'ozon')
            """,
            (),
        ),
        (
            "product_marketplace_status_tenant_rel",
            """
            UPDATE product_marketplace_status_tenant_rel
            SET ozon_present = FALSE,
                ozon_status = 'Нет данных',
                updated_at = NOW()
            WHERE organization_id = %s AND (ozon_present OR ozon_status <> 'Нет данных')
            """,
            (organization_id,),
        ),
        (
            "catalog_product_page_tenant_rel",
            """
            UPDATE catalog_product_page_tenant_rel
            SET ozon_present = FALSE,
                ozon_status = 'Нет данных',
                updated_at = NOW()
            WHERE organization_id = %s AND (ozon_present OR ozon_status <> 'Нет данных')
            """,
            (organization_id,),
        ),
        (
            "json_documents",
            """
            DELETE FROM json_documents
            WHERE path LIKE 'marketplaces/ozon/%%'
               OR path IN (
                 'marketplaces/ozon/category_attributes.json',
                 'marketplaces/ozon/categories_tree.json',
                 'marketplaces/ozon/import_products_info.json',
                 'marketplaces/ozon/product_rating_by_sku.json'
               )
            """,
            (),
        ),
    ]
    changed: dict[str, int] = {}
    for table, sql, params in statements:
        if not table_exists(cur, table):
            changed[table] = 0
            continue
        cur.execute(sql, params)
        changed[table] = int(cur.rowcount or 0)
    return changed


def main() -> None:
    dsn = env_value("DATABASE_URL") or env_value("PIM_DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is missing")
    organization_id = os.getenv("ORGANIZATION_ID", DEFAULT_ORG_ID).strip() or DEFAULT_ORG_ID
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"pre-ozon-cleanup-{organization_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json.gz"

    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            before = backup_touched_rows(cur, organization_id, backup_path)
            changed = cleanup_ozon(cur, organization_id)
            after = backup_touched_rows(cur, organization_id, backup_path.with_name(backup_path.name.replace("pre-", "post-")))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("organization_id=" + organization_id)
    print("backup=" + str(backup_path))
    print("before=" + json.dumps(before, ensure_ascii=False, sort_keys=True))
    print("changed=" + json.dumps(changed, ensure_ascii=False, sort_keys=True))
    print("after=" + json.dumps(after, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
