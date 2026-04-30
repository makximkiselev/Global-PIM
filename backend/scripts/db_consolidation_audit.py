#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT_DIR / "backend" / ".env"

EXPECTED_RUNTIME_TABLES = {
    "attribute_mappings_rel",
    "attribute_mappings_tenant_rel",
    "attribute_value_refs_rel",
    "attribute_value_refs_tenant_rel",
    "catalog_nodes_rel",
    "catalog_product_page_rel",
    "catalog_product_page_tenant_rel",
    "catalog_product_registry_rel",
    "category_mappings_rel",
    "category_mappings_tenant_rel",
    "category_product_counts_rel",
    "category_template_links_rel",
    "category_template_links_tenant_rel",
    "category_template_resolution_rel",
    "category_template_resolution_tenant_rel",
    "connector_import_stores_rel",
    "connector_import_stores_tenant_rel",
    "connector_method_state_rel",
    "connector_method_state_tenant_rel",
    "connector_provider_settings_rel",
    "connector_provider_settings_tenant_rel",
    "dashboard_stats_rel",
    "dictionaries_rel",
    "dictionaries_tenant_rel",
    "dictionary_aliases_rel",
    "dictionary_aliases_tenant_rel",
    "dictionary_export_maps_rel",
    "dictionary_export_maps_tenant_rel",
    "dictionary_provider_refs_rel",
    "dictionary_provider_refs_tenant_rel",
    "dictionary_value_sources_rel",
    "dictionary_value_sources_tenant_rel",
    "dictionary_values_rel",
    "dictionary_values_tenant_rel",
    "json_documents",
    "organization_invites",
    "organization_members",
    "organizations",
    "platform_roles",
    "platform_user_roles",
    "platform_users",
    "product_group_variant_params_rel",
    "product_groups_rel",
    "product_marketplace_status_rel",
    "product_marketplace_status_tenant_rel",
    "product_variants_rel",
    "products_rel",
    "template_attributes_rel",
    "template_attributes_tenant_rel",
    "templates_rel",
    "templates_tenant_rel",
    "tenant_provisioning_jobs",
    "tenant_registry",
}

TENANT_TABLES = (
    "catalog_product_page_tenant_rel",
    "product_marketplace_status_tenant_rel",
    "category_template_resolution_tenant_rel",
    "attribute_mappings_tenant_rel",
    "attribute_value_refs_tenant_rel",
    "templates_tenant_rel",
    "dictionaries_tenant_rel",
)

CONTROL_PLANE_CLEANUP_TABLES = (
    "tenant_provisioning_jobs",
    "tenant_registry",
    "organization_invites",
    "organization_members",
)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key] = value
    return values


def database_url() -> str:
    env = load_env(BACKEND_ENV)
    return os.getenv("DATABASE_URL", "").strip() or env.get("DATABASE_URL", "").strip()


def connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore

        return psycopg.connect(dsn)
    except Exception:
        try:
            import psycopg2  # type: ignore

            return psycopg2.connect(dsn)
        except Exception as exc:
            raise RuntimeError("Install psycopg or psycopg2 to run DB audit") from exc


def fetch_all(cur: Any, query: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
    cur.execute(query, tuple(params))
    return list(cur.fetchall())


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def table_exists(cur: Any, table: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    )
    return cur.fetchone() is not None


def count_table(cur: Any, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}")
    return int(cur.fetchone()[0])


def load_json_doc(cur: Any, path: str) -> Any | None:
    if not table_exists(cur, "json_documents"):
        return None
    cur.execute("SELECT payload FROM json_documents WHERE path = %s", (path,))
    row = cur.fetchone()
    if not row:
        return None
    payload = row[0]
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return None
    return payload


def product_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def catalog_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("nodes")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def print_report(cur: Any) -> int:
    tables = [row[0] for row in fetch_all(cur, """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)]
    table_set = set(tables)
    backup_tables = sorted(t for t in tables if t.startswith("backup_"))
    unexpected_tables = sorted(table_set - EXPECTED_RUNTIME_TABLES)
    missing_tables = sorted(EXPECTED_RUNTIME_TABLES - table_set)

    print("== DB consolidation audit ==")
    print(f"tables.total={len(tables)}")
    print(f"tables.expected_runtime={len(EXPECTED_RUNTIME_TABLES)}")
    print(f"tables.backup={len(backup_tables)}")
    print(f"tables.unexpected={len(unexpected_tables)}")
    print(f"tables.missing={len(missing_tables)}")

    if missing_tables:
        print("\n-- missing runtime tables --")
        for table in missing_tables:
            print(table)

    if unexpected_tables:
        print("\n-- unexpected tables --")
        for table in unexpected_tables:
            print(f"{table}\trows={count_table(cur, table)}")

    if table_exists(cur, "organizations"):
        print("\n-- organizations by status --")
        for status, count in fetch_all(cur, "SELECT status, COUNT(*) FROM organizations GROUP BY status ORDER BY status"):
            print(f"{status}\t{count}")

    print("\n-- key table counts --")
    for table in (
        "catalog_nodes_rel",
        "products_rel",
        "product_groups_rel",
        "product_variants_rel",
        "catalog_product_page_tenant_rel",
        "product_marketplace_status_tenant_rel",
        "json_documents",
    ):
        if table_exists(cur, table):
            print(f"{table}\t{count_table(cur, table)}")

    print("\n-- tenant row distribution --")
    for table in TENANT_TABLES:
        if not table_exists(cur, table):
            continue
        print(f"[{table}]")
        for org_id, count in fetch_all(
            cur,
            f"SELECT organization_id, COUNT(*) FROM {quote_ident(table)} GROUP BY organization_id ORDER BY COUNT(*) DESC, organization_id",
        ):
            print(f"{org_id}\t{count}")

    print("\n-- parity checks --")
    products_json = product_items(load_json_doc(cur, "products.json"))
    products_rel_count = count_table(cur, "products_rel") if table_exists(cur, "products_rel") else 0
    print(f"products.rel={products_rel_count} products.json={len(products_json)} delta={products_rel_count - len(products_json)}")

    catalog_json = catalog_items(load_json_doc(cur, "catalog_nodes.json"))
    catalog_rel_count = count_table(cur, "catalog_nodes_rel") if table_exists(cur, "catalog_nodes_rel") else 0
    print(f"catalog.rel={catalog_rel_count} catalog.json={len(catalog_json)} delta={catalog_rel_count - len(catalog_json)}")

    return 0


def print_cleanup_sql(cur: Any) -> int:
    backup_tables = [row[0] for row in fetch_all(cur, """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name LIKE %s ESCAPE '\\'
        ORDER BY table_name
    """, ("backup\\_%",))]

    stale_orgs: list[str] = []
    if table_exists(cur, "organizations"):
        stale_orgs = [row[0] for row in fetch_all(cur, """
            SELECT id
            FROM organizations
            WHERE status = 'provisioning' AND id <> 'org_default'
            ORDER BY id
        """)]

    tenant_cleanup_tables = [
        row[0] for row in fetch_all(cur, """
            SELECT table_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'organization_id'
              AND table_name NOT LIKE %s ESCAPE '\\'
              AND table_name <> ALL(%s)
            GROUP BY table_name
            ORDER BY table_name
        """, ("backup\\_%", list(CONTROL_PLANE_CLEANUP_TABLES + ("organizations",))))
    ]

    print("-- Review-only cleanup SQL. Do not run without a fresh backup and parity sign-off.")
    print("-- Safety: the guard block and final ROLLBACK make this output non-destructive if pasted as-is.")
    print("BEGIN;")
    print("DO $$")
    print("BEGIN")
    print("  RAISE EXCEPTION 'Review-only cleanup SQL: remove this guard and change ROLLBACK to COMMIT only after approval';")
    print("END $$;")

    for table in backup_tables:
        print(f"DROP TABLE IF EXISTS {quote_ident(table)};")

    if stale_orgs:
        orgs = ", ".join(quote_literal(str(org)) for org in stale_orgs)
        for table in tenant_cleanup_tables:
            print(f"DELETE FROM {quote_ident(table)} WHERE organization_id IN ({orgs});")
        for table in CONTROL_PLANE_CLEANUP_TABLES:
            if table_exists(cur, table):
                print(f"DELETE FROM {quote_ident(table)} WHERE organization_id IN ({orgs});")
        print(f"DELETE FROM organizations WHERE id IN ({orgs});")

    print("ROLLBACK;")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only DB audit for SmartPim consolidation.")
    parser.add_argument("--cleanup-sql", action="store_true", help="Print review-only cleanup SQL for backup tables and stale orgs.")
    args = parser.parse_args()

    dsn = database_url()
    if not dsn:
        print("DATABASE_URL is missing", file=sys.stderr)
        return 2

    conn = connect(dsn)
    try:
        with conn.cursor() as cur:
            if args.cleanup_sql:
                return print_cleanup_sql(cur)
            return print_report(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
