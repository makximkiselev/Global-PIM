#!/usr/bin/env python3
from __future__ import annotations

import gzip
import json
import subprocess
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


APP_DIR = Path("/opt/projects/global-pim")
ENV_FILE = APP_DIR / "backend" / ".env"
BACKUP_DIR = APP_DIR / "backups"
OWNER_LOGIN = "owner"
OWNER_EMAIL = "owner@local.invalid"

KEEP_JSON_PATHS = {
    "auth/access.json",
    "auth/sessions.json",
    "auth/login_events.json",
    "catalog_nodes.json",
    "catalog_products.json",
    "products.json",
    "product_groups.json",
    "product_variants.json",
    "product_category_index.json",
    "sku_gt_index.json",
    "sku_index.json",
    "sku_pim_index.json",
    "variant_key_index.json",
    "counters.json",
}

DELETE_TABLES = [
    "attribute_provider_bindings_tenant_rel",
    "attribute_provider_bindings_rel",
    "attribute_value_refs_tenant_rel",
    "attribute_value_refs_rel",
    "attribute_mappings_tenant_rel",
    "attribute_mappings_rel",
    "category_mappings_tenant_rel",
    "category_mappings_rel",
    "category_template_links_tenant_rel",
    "category_template_links_rel",
    "category_template_resolution_tenant_rel",
    "category_template_resolution_rel",
    "template_attributes_tenant_rel",
    "template_attributes_rel",
    "templates_tenant_rel",
    "templates_rel",
    "dictionaries_tenant_rel",
    "dictionaries_rel",
    "dictionary_values_tenant_rel",
    "dictionary_values_rel",
    "dictionary_aliases_tenant_rel",
    "dictionary_aliases_rel",
    "dictionary_provider_refs_tenant_rel",
    "dictionary_provider_refs_rel",
    "dictionary_export_maps_tenant_rel",
    "dictionary_export_maps_rel",
    "dictionary_value_sources_tenant_rel",
    "dictionary_value_sources_rel",
    "pim_channel_links",
    "pim_workflow_runs",
    "product_marketplace_status_tenant_rel",
    "product_marketplace_status_rel",
    "catalog_product_page_tenant_rel",
    "catalog_product_page_rel",
    "category_product_counts_rel",
    "dashboard_stats_rel",
    "connector_import_stores_tenant_rel",
    "connector_import_stores_rel",
    "connector_method_state_tenant_rel",
    "connector_method_state_rel",
    "connector_provider_settings_tenant_rel",
    "connector_provider_settings_rel",
    "organization_invites",
]


def env_value(key: str) -> str:
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


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def connect(dsn: str) -> Any:
    if psycopg is not None:
        return psycopg.connect(dsn)
    if psycopg2 is not None:
        return psycopg2.connect(dsn)
    raise RuntimeError("psycopg or psycopg2 is required")


def fetch_table_names(cur: Any) -> list[str]:
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
    return [row[0] for row in cur.fetchall()]


def count_table(cur: Any, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}")
    return int((cur.fetchone() or [0])[0] or 0)


def backup_database(conn: Any, backup_path: Path) -> dict[str, int]:
    payload: dict[str, Any] = {"table_order": [], "counts_before": {}, "tables": {}}
    with conn.cursor() as cur:
        table_names = fetch_table_names(cur)
        payload["table_order"] = table_names
        for table in table_names:
            cur.execute(f"SELECT * FROM {quote_ident(table)}")
            columns = [getattr(desc, "name", None) or desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            payload["tables"][table] = rows
            payload["counts_before"][table] = len(rows)
    with gzip.open(backup_path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=json_default)
    return dict(payload["counts_before"])


def set_workers(action: str) -> None:
    subprocess.run(
        [
            "systemctl",
            action,
            "global-pim-ai-match-worker.service",
            "global-pim-value-ai-worker.service",
            "global-pim-export-worker.service",
        ],
        check=False,
    )


def reset_runtime_data(conn: Any) -> tuple[dict[str, int], dict[str, int]]:
    before: dict[str, int] = {}
    after: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in [*DELETE_TABLES, "json_documents"]:
            before[table] = count_table(cur, table)

        cur.execute("BEGIN")
        for table in DELETE_TABLES:
            cur.execute(f"DELETE FROM {quote_ident(table)}")
        cur.execute("DELETE FROM json_documents WHERE NOT (path = ANY(%s))", (list(KEEP_JSON_PATHS),))
        cur.execute(
            """
            UPDATE users
            SET role_ids = jsonb_build_array('role_owner'),
                status = 'active',
                is_active = TRUE,
                updated_at = NOW()
            WHERE lower(login) = lower(%s)
               OR lower(email) = lower(%s)
            """,
            (OWNER_LOGIN, OWNER_EMAIL),
        )
        cur.execute(
            """
            INSERT INTO organizations (id, slug, name, status, tenant_status, created_at, updated_at)
            VALUES
              ('org_gsm_king', 'gsm-king', 'GSM King', 'active', 'ready', NOW(), NOW()),
              ('org_device_mall', 'device-mall', 'Девайс Молл', 'active', 'ready', NOW(), NOW())
            ON CONFLICT (id) DO UPDATE
            SET slug = EXCLUDED.slug,
                name = EXCLUDED.name,
                status = 'active',
                tenant_status = 'ready',
                updated_at = NOW()
            """
        )
        cur.execute(
            """
            WITH target_user AS (
              SELECT id
              FROM users
              WHERE lower(login) = lower(%s) OR lower(email) = lower(%s)
              LIMIT 1
            ), target_orgs AS (
              SELECT id FROM organizations
            )
            INSERT INTO organization_members (id, organization_id, user_id, org_role_code, status, created_at, updated_at)
            SELECT 'org_member_' || md5(o.id || ':' || u.id), o.id, u.id, 'org_owner', 'active', NOW(), NOW()
            FROM target_orgs o CROSS JOIN target_user u
            ON CONFLICT (organization_id, user_id) DO UPDATE
            SET org_role_code = 'org_owner',
                status = 'active',
                updated_at = NOW()
            """
            ,
            (OWNER_LOGIN, OWNER_EMAIL),
        )
        cur.execute("COMMIT")

        for table in [*DELETE_TABLES, "json_documents"]:
            after[table] = count_table(cur, table)
    return before, after


def main() -> None:
    dsn = env_value("DATABASE_URL") or env_value("PIM_DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is missing")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"pre-catalog-only-reset-{stamp}.json.gz"

    set_workers("stop")
    try:
        conn = connect(dsn)
        try:
            backup_counts = backup_database(conn, backup_path)
            deleted_before, deleted_after = reset_runtime_data(conn)
        finally:
            conn.close()
    finally:
        set_workers("start")

    print("backup=" + str(backup_path))
    print("preserved_catalog_nodes_rel=" + str(backup_counts.get("catalog_nodes_rel")))
    print("preserved_products_rel=" + str(backup_counts.get("products_rel")))
    print("preserved_product_groups_rel=" + str(backup_counts.get("product_groups_rel")))
    print("deleted_before=" + json.dumps(deleted_before, ensure_ascii=False, sort_keys=True))
    print("deleted_after=" + json.dumps(deleted_after, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
