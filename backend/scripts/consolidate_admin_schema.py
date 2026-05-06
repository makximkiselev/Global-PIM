#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT_DIR / "backend" / ".env"


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
            raise RuntimeError("Install psycopg or psycopg2 to run schema consolidation") from exc


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


def column_exists(cur: Any, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def json_param(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def fetch_json_doc(cur: Any, path: str) -> Any:
    if not table_exists(cur, "json_documents"):
        return None
    cur.execute("SELECT payload FROM json_documents WHERE path = %s", (path,))
    row = cur.fetchone()
    if not row:
        return None
    payload = row[0]
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def drop_constraints_referencing(cur: Any, referenced_table: str) -> None:
    cur.execute(
        """
        SELECT conrelid::regclass::text AS table_name, conname
        FROM pg_constraint
        WHERE confrelid = %s::regclass
        """,
        (referenced_table,),
    )
    for table_name, constraint_name in cur.fetchall() or []:
        cur.execute(f'ALTER TABLE "{str(table_name).replace(chr(34), chr(34) + chr(34))}" DROP CONSTRAINT IF EXISTS "{str(constraint_name).replace(chr(34), chr(34) + chr(34))}"')


def constraint_exists(cur: Any, table: str, constraint: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = %s::regclass
          AND conname = %s
        """,
        (table, constraint),
    )
    return cur.fetchone() is not None


def add_constraint(cur: Any, table: str, constraint: str, sql: str) -> None:
    if constraint_exists(cur, table, constraint):
        return
    cur.execute(sql)


def apply_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS roles (
          id TEXT PRIMARY KEY,
          code TEXT NOT NULL UNIQUE,
          name TEXT NOT NULL,
          description TEXT NULL,
          pages JSONB NOT NULL DEFAULT '[]'::jsonb,
          actions JSONB NOT NULL DEFAULT '[]'::jsonb,
          is_system BOOLEAN NOT NULL DEFAULT FALSE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY,
          login TEXT NOT NULL DEFAULT '',
          email TEXT NOT NULL DEFAULT '',
          name TEXT NOT NULL,
          password_hash TEXT NOT NULL DEFAULT '',
          password_salt TEXT NOT NULL DEFAULT '',
          role_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
          is_active BOOLEAN NOT NULL DEFAULT TRUE,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          last_login_at TIMESTAMPTZ NULL,
          last_login_ip TEXT NULL,
          last_user_agent TEXT NULL
        )
        """
    )
    for ddl in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_salt TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_ip TEXT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_user_agent TEXT NULL",
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS pages JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS actions JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE roles ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS tenant_status TEXT NULL",
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS provisioning_error TEXT NULL",
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS schema_version TEXT NULL",
    ]:
        cur.execute(ddl)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_login ON users ((lower(login)))")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lower_email_non_empty ON users ((lower(email))) WHERE email <> ''")


def migrate_auth_doc(cur: Any) -> None:
    doc = fetch_json_doc(cur, "auth/access.json")
    if not isinstance(doc, dict):
        return
    roles = doc.get("roles") if isinstance(doc.get("roles"), dict) else {}
    users = doc.get("users") if isinstance(doc.get("users"), dict) else {}
    for role in roles.values():
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("id") or "").strip()
        code = str(role.get("code") or "").strip()
        if not role_id or not code:
            continue
        cur.execute(
            """
            INSERT INTO roles (id, code, name, description, pages, actions, is_system, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, COALESCE(%s::timestamptz, NOW()), COALESCE(%s::timestamptz, NOW()))
            ON CONFLICT (id) DO UPDATE
            SET code = EXCLUDED.code,
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                pages = EXCLUDED.pages,
                actions = EXCLUDED.actions,
                is_system = EXCLUDED.is_system,
                updated_at = NOW()
            """,
            (
                role_id,
                code,
                str(role.get("name") or code).strip(),
                str(role.get("description") or "").strip(),
                json_param(role.get("pages") if isinstance(role.get("pages"), list) else []),
                json_param(role.get("actions") if isinstance(role.get("actions"), list) else []),
                bool(role.get("is_system")),
                role.get("created_at"),
                role.get("updated_at"),
            ),
        )
    for user in users.values():
        if not isinstance(user, dict):
            continue
        user_id = str(user.get("id") or "").strip()
        login = str(user.get("login") or user.get("email") or "").strip().lower()
        if not user_id or not login:
            continue
        cur.execute(
            """
            INSERT INTO users (
              id, login, email, name, password_hash, password_salt, role_ids, is_active, status,
              created_at, updated_at, last_login_at, last_login_ip, last_user_agent
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, COALESCE(%s::timestamptz, NOW()), COALESCE(%s::timestamptz, NOW()), %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET login = EXCLUDED.login,
                email = EXCLUDED.email,
                name = EXCLUDED.name,
                password_hash = COALESCE(NULLIF(EXCLUDED.password_hash, ''), users.password_hash),
                password_salt = COALESCE(NULLIF(EXCLUDED.password_salt, ''), users.password_salt),
                role_ids = EXCLUDED.role_ids,
                is_active = EXCLUDED.is_active,
                status = EXCLUDED.status,
                updated_at = NOW(),
                last_login_at = COALESCE(EXCLUDED.last_login_at, users.last_login_at),
                last_login_ip = COALESCE(EXCLUDED.last_login_ip, users.last_login_ip),
                last_user_agent = COALESCE(EXCLUDED.last_user_agent, users.last_user_agent)
            """,
            (
                user_id,
                login,
                str(user.get("email") or "").strip().lower(),
                str(user.get("name") or login).strip(),
                str(user.get("password_hash") or "").strip(),
                str(user.get("password_salt") or "").strip(),
                json_param([str(x) for x in (user.get("role_ids") or []) if str(x).strip()]),
                bool(user.get("is_active", True)),
                "active" if bool(user.get("is_active", True)) else "disabled",
                user.get("created_at"),
                user.get("updated_at"),
                user.get("last_login_at"),
                str(user.get("last_login_ip") or "").strip(),
                str(user.get("last_user_agent") or "").strip(),
            ),
        )


def migrate_legacy_tables(cur: Any) -> None:
    if table_exists(cur, "platform_users"):
        cur.execute(
            """
            INSERT INTO users (id, login, email, name, password_hash, status, created_at, updated_at, last_login_at)
            SELECT id, lower(COALESCE(NULLIF(email, ''), id)), COALESCE(email, ''), name, COALESCE(password_hash, ''), status, created_at, updated_at, last_login_at
            FROM platform_users
            ON CONFLICT (id) DO NOTHING
            """
        )
    if table_exists(cur, "tenant_registry"):
        cur.execute(
            """
            UPDATE organizations o
            SET tenant_status = tr.status,
                schema_version = tr.schema_version
            FROM tenant_registry tr
            WHERE tr.organization_id = o.id
            """
        )
    if table_exists(cur, "tenant_provisioning_jobs"):
        cur.execute(
            """
            UPDATE organizations o
            SET provisioning_error = j.error,
                tenant_status = COALESCE(o.tenant_status, j.status)
            FROM (
              SELECT DISTINCT ON (organization_id) organization_id, status, error
              FROM tenant_provisioning_jobs
              ORDER BY organization_id, created_at DESC, id DESC
            ) j
            WHERE j.organization_id = o.id
            """
        )
    if table_exists(cur, "organization_members"):
        if not column_exists(cur, "organization_members", "user_id"):
            cur.execute("ALTER TABLE organization_members ADD COLUMN user_id TEXT NULL")
        if column_exists(cur, "organization_members", "platform_user_id"):
            cur.execute("UPDATE organization_members SET user_id = platform_user_id WHERE user_id IS NULL")
            cur.execute("ALTER TABLE organization_members DROP COLUMN platform_user_id CASCADE")
        cur.execute("DELETE FROM organization_members WHERE user_id IS NULL OR user_id = ''")
        cur.execute("ALTER TABLE organization_members ALTER COLUMN user_id SET NOT NULL")
        cur.execute("DROP INDEX IF EXISTS idx_organization_members_unique")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_organization_members_unique ON organization_members (organization_id, user_id)")
        add_constraint(
            cur,
            "organization_members",
            "organization_members_user_id_fkey",
            "ALTER TABLE organization_members ADD CONSTRAINT organization_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE",
        )
    for referenced in ("platform_users", "platform_roles"):
        if table_exists(cur, referenced):
            drop_constraints_referencing(cur, referenced)
    add_constraint(
        cur,
        "organization_invites",
        "organization_invites_created_by_user_id_fkey",
        "ALTER TABLE organization_invites ADD CONSTRAINT organization_invites_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES users(id)",
    )
    add_constraint(
        cur,
        "organization_invites",
        "organization_invites_accepted_by_user_id_fkey",
        "ALTER TABLE organization_invites ADD CONSTRAINT organization_invites_accepted_by_user_id_fkey FOREIGN KEY (accepted_by_user_id) REFERENCES users(id)",
    )
    for table in ("platform_user_roles", "user_roles", "platform_roles", "platform_users", "tenant_provisioning_jobs", "tenant_registry"):
        cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')


def count(cur: Any, table: str) -> int:
    if not table_exists(cur, table):
        return 0
    cur.execute(f'SELECT COUNT(*) FROM "{table}"')
    return int(cur.fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidate auth/admin DB schema to users, roles, organizations, members, invites.")
    parser.add_argument("--apply", action="store_true", help="Apply migration. Default is dry-run.")
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
            apply_schema(cur)
            migrate_auth_doc(cur)
            migrate_legacy_tables(cur)
            summary = {
                "users": count(cur, "users"),
                "roles": count(cur, "roles"),
                "organizations": count(cur, "organizations"),
                "organization_members": count(cur, "organization_members"),
                "organization_invites": count(cur, "organization_invites"),
                "platform_users": int(table_exists(cur, "platform_users")),
                "platform_roles": int(table_exists(cur, "platform_roles")),
                "platform_user_roles": int(table_exists(cur, "platform_user_roles")),
                "tenant_registry": int(table_exists(cur, "tenant_registry")),
                "tenant_provisioning_jobs": int(table_exists(cur, "tenant_provisioning_jobs")),
            }
        if args.apply:
            conn.commit()
            print("mode=apply")
        else:
            conn.rollback()
            print("mode=dry-run")
        for key, value in summary.items():
            print(f"{key}={value}")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
