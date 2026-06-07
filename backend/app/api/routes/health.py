from typing import Any, Dict, List

from fastapi import APIRouter

from app.core.json_store import _is_retryable_pg_error, _pg_connect, _reset_pg_connection, _storage_backend

from app.core.object_storage import ObjectStorageError, s3_enabled

router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True}


@router.get("/health/storage")
def storage_health():
    try:
        enabled = s3_enabled()
    except ObjectStorageError as exc:
        return {"ok": False, "s3_enabled": False, "error": str(exc)}
    return {"ok": bool(enabled), "s3_enabled": bool(enabled)}


@router.get("/health/db-grants")
def db_grants_health() -> Dict[str, Any]:
    if _storage_backend() != "postgres":
        return {"ok": True, "backend": _storage_backend(), "skipped": True}

    probe_path = "__health/db_grants_probe.json"
    checks: List[str] = []
    for attempt in range(2):
        try:
            conn, _, _ = _pg_connect()
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, current_database()")
                identity = cur.fetchone()
                cur.execute(
                    """
                    SELECT has_schema_privilege(current_user, 'public', 'USAGE') AS can_use_schema,
                           has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_schema
                    """
                )
                schema_privileges = cur.fetchone()
                cur.execute(
                    """
                    SELECT tablename,
                           has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'SELECT') AS can_select,
                           has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'INSERT') AS can_insert,
                           has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'UPDATE') AS can_update,
                           has_table_privilege(current_user, format('%I.%I', schemaname, tablename), 'DELETE') AS can_delete
                      FROM pg_tables
                     WHERE schemaname = 'public'
                     ORDER BY tablename
                    """
                )
                missing: List[Dict[str, Any]] = []
                if schema_privileges and not bool(schema_privileges[0]):
                    missing.append({"schema": "public", "missing": ["USAGE"]})
                if schema_privileges and not bool(schema_privileges[1]):
                    missing.append({"schema": "public", "missing": ["CREATE"]})
                for row in cur.fetchall():
                    table = str(row[0])
                    missing_privileges = [
                        name
                        for name, granted in (
                            ("SELECT", row[1]),
                            ("INSERT", row[2]),
                            ("UPDATE", row[3]),
                            ("DELETE", row[4]),
                        )
                        if not bool(granted)
                    ]
                    if missing_privileges:
                        missing.append({"table": table, "missing": missing_privileges})

                cur.execute("SELECT COUNT(*) FROM json_documents")
                checks.append("json_documents_select")
                cur.execute(
                    """
                    INSERT INTO json_documents (path, payload, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (path) DO UPDATE
                       SET payload = EXCLUDED.payload,
                           updated_at = NOW()
                    """,
                    (probe_path, '{"ok": true, "check": "insert_update"}'),
                )
                checks.append("json_documents_insert_update")
                cur.execute("DELETE FROM json_documents WHERE path = %s", (probe_path,))
                checks.append("json_documents_delete")

            return {
                "ok": not missing,
                "backend": "postgres",
                "user": identity[0] if identity else "",
                "database": identity[1] if identity else "",
                "checks": checks,
                "missing": missing,
            }
        except Exception as exc:
            if attempt == 0 and _is_retryable_pg_error(exc):
                _reset_pg_connection()
                checks = []
                continue
            return {
                "ok": False,
                "backend": "postgres",
                "checks": checks,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }

    return {"ok": False, "backend": "postgres", "checks": checks, "error": "DB_GRANTS_CHECK_RETRY_EXHAUSTED"}
