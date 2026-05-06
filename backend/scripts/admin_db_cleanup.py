#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT_DIR / "backend" / ".env"

BACKUP_TABLE_RE = re.compile(
    r"^backup_20260428_\d+_(organization_invites|organization_members|organizations|platform_users)$"
)
TEST_ORG_MARKERS = (
    "test",
    "qa",
    "verify",
    "shot",
    "shell",
    "catalog",
    "full",
    "view",
    "codex",
    "control-center",
)
KEEP_ORG_ID = "org_default"
KEEP_ORG_NAME = "Global Trade"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key.strip()] = value
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
            raise RuntimeError("Install psycopg or psycopg2 to run admin DB cleanup") from exc


def fetch_all(cur: Any, query: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
    cur.execute(query, tuple(params))
    return list(cur.fetchall())


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def count_table(cur: Any, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}")
    return int(cur.fetchone()[0])


def backup_tables(cur: Any) -> list[tuple[str, int]]:
    rows = fetch_all(
        cur,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name LIKE %s
        ORDER BY table_name
        """,
        ("backup_20260428_%",),
    )
    out: list[tuple[str, int]] = []
    for (table_name,) in rows:
        table = str(table_name)
        if BACKUP_TABLE_RE.match(table):
            out.append((table, count_table(cur, table)))
    return out


def cleanup_organizations(cur: Any) -> list[tuple[str, str, str, str]]:
    rows = fetch_all(
        cur,
        """
        SELECT id, slug, name, status
        FROM organizations
        WHERE id <> %s
          AND status = 'provisioning'
        ORDER BY id
        """,
        (KEEP_ORG_ID,),
    )
    out: list[tuple[str, str, str, str]] = []
    for org_id, slug, name, status in rows:
        normalized = f"{slug or ''} {name or ''}".lower()
        if any(marker in normalized for marker in TEST_ORG_MARKERS):
            out.append((str(org_id), str(slug), str(name), str(status)))
    return out


def print_plan(tables: list[tuple[str, int]], orgs: list[tuple[str, str, str, str]]) -> None:
    print("admin_db_cleanup_plan")
    print(f"backup_tables={len(tables)}")
    for table, rows in tables:
        print(f"  drop_table {table} rows={rows}")
    print(f"test_provisioning_organizations={len(orgs)}")
    for org_id, slug, name, status in orgs:
        print(f"  delete_org {org_id} slug={slug} name={name} status={status}")


def assert_default_org(cur: Any) -> None:
    rows = fetch_all(cur, "SELECT id, name, status FROM organizations WHERE id = %s", (KEEP_ORG_ID,))
    if len(rows) != 1:
        raise RuntimeError(f"Expected {KEEP_ORG_ID} to exist exactly once")
    _, name, status = rows[0]
    if str(name) != KEEP_ORG_NAME or str(status) != "active":
        raise RuntimeError(f"Refusing cleanup: {KEEP_ORG_ID} is not active {KEEP_ORG_NAME}")


def apply_cleanup(conn: Any, tables: list[tuple[str, int]], orgs: list[tuple[str, str, str, str]]) -> None:
    with conn.cursor() as cur:
        assert_default_org(cur)
        org_ids = [org_id for org_id, *_ in orgs]
        if org_ids:
            cur.execute("DELETE FROM organizations WHERE id = ANY(%s)", (org_ids,))
        for table, _rows in tables:
            cur.execute(f"DROP TABLE IF EXISTS {quote_ident(table)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely clean obsolete admin/control-plane DB artifacts.")
    parser.add_argument("--apply", action="store_true", help="Apply cleanup. Default is dry-run.")
    args = parser.parse_args()

    dsn = database_url()
    if not dsn:
        print("DATABASE_URL is missing", file=sys.stderr)
        return 2

    conn = connect(dsn)
    try:
        if hasattr(conn, "autocommit"):
            conn.autocommit = False
        with conn.cursor() as cur:
            assert_default_org(cur)
            tables = backup_tables(cur)
            orgs = cleanup_organizations(cur)
        print_plan(tables, orgs)
        if not args.apply:
            print("mode=dry-run")
            return 0
        apply_cleanup(conn, tables, orgs)
        conn.commit()
        print("mode=apply")
        print("status=applied")
        return 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
