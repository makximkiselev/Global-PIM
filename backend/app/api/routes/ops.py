from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Request

from app.api.routes import connectors_status
from app.core.auth import auth_from_request, has_action
from app.core.json_store import _pg_connect
from app.core.object_storage import ObjectStorageError, s3_enabled
from app.core.tenant_context import current_tenant_organization_id

router = APIRouter(prefix="/ops", tags=["ops"])


WORKFLOW_LABELS = {
    "marketplace_attribute_ai_match": "AI сопоставление параметров",
    "marketplace_value_ai_match": "AI сопоставление значений",
    "marketplace_export_semantics_ai": "AI аудит выгрузки",
    "catalog_export_prepare": "Подготовка экспорта",
    "competitor_discovery": "Поиск конкурентов",
}


def _extract_rows(cur: Any) -> List[Dict[str, Any]]:
    columns = [str((item or [None])[0] or "") for item in (cur.description or [])]
    rows: List[Dict[str, Any]] = []
    for raw in cur.fetchall() or []:
        if isinstance(raw, dict):
            rows.append({str(key): raw[key] for key in raw.keys()})
        else:
            rows.append({columns[idx]: raw[idx] for idx in range(min(len(columns), len(raw)))})
    return rows


def _section(status: str, title: str, detail: str = "", **extra: Any) -> Dict[str, Any]:
    return {"status": status, "title": title, "detail": detail, **extra}


def _require_ops_access(request: Request) -> None:
    auth = auth_from_request(request)
    if not auth.user:
        raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
    if not (has_action(auth, "users.manage") or has_action(auth, "roles.manage") or has_action(auth, "*")):
        raise HTTPException(status_code=403, detail="FORBIDDEN")


def _db_grants_section() -> Dict[str, Any]:
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        cur.execute("SELECT current_user AS current_user")
        current_user = str((_extract_rows(cur)[0] or {}).get("current_user") or "")
        cur.execute(
            """
            SELECT c.relkind, n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p', 'S', 'v', 'm')
              AND pg_get_userbyid(c.relowner) <> current_user
            ORDER BY n.nspname, c.relname
            LIMIT 20
            """
        )
        drift = _extract_rows(cur)
        cur.execute(
            """
            SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid) AS arguments, pg_get_userbyid(p.proowner) AS owner
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND pg_get_userbyid(p.proowner) <> current_user
            ORDER BY n.nspname, p.proname
            LIMIT 20
            """
        )
        function_drift = _extract_rows(cur)
    total = len(drift) + len(function_drift)
    return _section(
        "ok" if total == 0 else "warn",
        "Права БД",
        "Все объекты принадлежат текущей роли." if total == 0 else f"Есть объекты не под текущей ролью: {total}.",
        current_user=current_user,
        drift=drift,
        function_drift=function_drift,
    )


def _workflow_section() -> Dict[str, Any]:
    conn, _, _ = _pg_connect()
    org_id = current_tenant_organization_id()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT workflow, status, COUNT(*)::int AS count, MAX(updated_at) AS latest_at
            FROM pim_workflow_runs
            WHERE organization_id = %s
            GROUP BY workflow, status
            ORDER BY workflow, status
            """,
            [org_id],
        )
        summary = _extract_rows(cur)
        cur.execute(
            """
            SELECT workflow, status, run_id, updated_at, payload_json->>'error' AS error, payload_json->>'message' AS message
            FROM pim_workflow_runs
            WHERE organization_id = %s
              AND status IN ('failed', 'running', 'queued')
            ORDER BY updated_at DESC
            LIMIT 12
            """,
            [org_id],
        )
        recent = _extract_rows(cur)
    failed = sum(int(row.get("count") or 0) for row in summary if row.get("status") == "failed")
    running = sum(int(row.get("count") or 0) for row in summary if row.get("status") in {"queued", "running"})
    status = "critical" if failed else "warn" if running else "ok"
    detail = "Нет активных или упавших задач."
    if failed:
        detail = f"Есть упавшие workflow: {failed}."
    elif running:
        detail = f"В очереди или выполняется: {running}."
    return _section(
        status,
        "Workflow runs",
        detail,
        organization_id=org_id,
        labels=WORKFLOW_LABELS,
        summary=summary,
        recent=recent,
    )


def _table_size_section() -> Dict[str, Any]:
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              relname AS table_name,
              pg_total_relation_size(c.oid)::bigint AS total_bytes,
              pg_relation_size(c.oid)::bigint AS table_bytes,
              COALESCE(s.n_live_tup, 0)::bigint AS estimated_rows
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p')
            ORDER BY pg_total_relation_size(c.oid) DESC
            LIMIT 12
            """
        )
        rows = _extract_rows(cur)
    largest = int(rows[0].get("total_bytes") or 0) if rows else 0
    status = "warn" if largest > 1024 * 1024 * 1024 else "ok"
    return _section(
        status,
        "Размеры таблиц",
        "Крупных таблиц больше 1 ГБ не видно." if status == "ok" else "Есть таблицы больше 1 ГБ.",
        rows=rows,
    )


def _storage_section() -> Dict[str, Any]:
    try:
        enabled = bool(s3_enabled())
        return _section("ok" if enabled else "warn", "S3 / медиа", "S3 включен." if enabled else "S3 не настроен.", s3_enabled=enabled)
    except ObjectStorageError as exc:
        return _section("critical", "S3 / медиа", str(exc), s3_enabled=False)


def _marketplace_section() -> Dict[str, Any]:
    org_id = current_tenant_organization_id()
    state = connectors_status._load_state(org_id)  # noqa: SLF001 - operations endpoint summarizes connector state
    providers = state.get("providers") if isinstance(state.get("providers"), dict) else {}
    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    totals = {
        "stores": 0,
        "import_enabled": 0,
        "export_enabled": 0,
        "safe_test_enabled": 0,
        "access_ok": 0,
        "access_error": 0,
        "method_errors": 0,
    }
    for provider_code, provider_def in connectors_status.PROVIDERS_DEF.items():
        provider = providers.get(provider_code) if isinstance(providers, dict) else {}
        if not isinstance(provider, dict):
            provider = {}
        stores = provider.get("import_stores") if isinstance(provider.get("import_stores"), list) else []
        methods = provider.get("methods") if isinstance(provider.get("methods"), dict) else {}
        provider_row = {
            "provider": provider_code,
            "title": provider_def.get("title") or provider_code,
            "stores": [],
            "methods": [],
        }
        for raw_store in stores:
            if not isinstance(raw_store, dict):
                continue
            row = {
                "provider": provider_code,
                "store_id": str(raw_store.get("id") or ""),
                "title": str(raw_store.get("title") or raw_store.get("id") or ""),
                "enabled": bool(raw_store.get("enabled")),
                "export_enabled": bool(raw_store.get("export_enabled")),
                "safe_test_enabled": bool(raw_store.get("safe_test_enabled")),
                "last_check_at": raw_store.get("last_check_at"),
                "last_check_status": str(raw_store.get("last_check_status") or "idle"),
                "last_check_error": str(raw_store.get("last_check_error") or ""),
            }
            provider_row["stores"].append(row)
            totals["stores"] += 1
            if row["enabled"]:
                totals["import_enabled"] += 1
            if row["export_enabled"]:
                totals["export_enabled"] += 1
            if row["safe_test_enabled"]:
                totals["safe_test_enabled"] += 1
            if row["last_check_status"] == "ok":
                totals["access_ok"] += 1
            if row["last_check_status"] == "error":
                totals["access_error"] += 1
                errors.append({
                    "scope": "store",
                    "provider": provider_code,
                    "store_id": row["store_id"],
                    "title": row["title"],
                    "error": row["last_check_error"],
                    "at": row["last_check_at"],
                })
        for method_code, method_title in provider_def.get("methods", {}).items():
            method = methods.get(method_code) if isinstance(methods, dict) else {}
            if not isinstance(method, dict):
                method = {}
            method_status = str(method.get("status") or "ok")
            method_row = {
                "provider": provider_code,
                "code": method_code,
                "title": method_title,
                "status": method_status,
                "last_run_at": method.get("last_run_at"),
                "last_error_at": method.get("last_error_at"),
                "last_error": str(method.get("last_error") or ""),
            }
            provider_row["methods"].append(method_row)
            if method_status != "ok":
                totals["method_errors"] += 1
                errors.append({
                    "scope": "method",
                    "provider": provider_code,
                    "method": method_code,
                    "title": method_title,
                    "error": method_row["last_error"],
                    "at": method_row["last_error_at"] or method_row["last_run_at"],
                })
        rows.append(provider_row)
    status = "critical" if totals["access_error"] or totals["method_errors"] else "warn" if totals["stores"] and not totals["export_enabled"] else "ok"
    if status == "critical":
        detail = "Есть ошибки доступа или импорта данных площадок."
    elif status == "warn":
        detail = "Магазины есть, но ни один не включен для экспорта."
    else:
        detail = "Магазины и процессы площадок без явных ошибок."
    return _section(status, "Маркетплейсы", detail, totals=totals, providers=rows, errors=errors[:20])


def _safe_section(fn: Any) -> Dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return _section("critical", getattr(fn, "__name__", "section"), str(exc))


@router.get("/status")
def ops_status(request: Request) -> Dict[str, Any]:
    _require_ops_access(request)
    sections = {
        "db_grants": _safe_section(_db_grants_section),
        "storage": _safe_section(_storage_section),
        "marketplaces": _safe_section(_marketplace_section),
        "workflows": _safe_section(_workflow_section),
        "table_sizes": _safe_section(_table_size_section),
    }
    if any(section.get("status") == "critical" for section in sections.values()):
        status = "critical"
    elif any(section.get("status") == "warn" for section in sections.values()):
        status = "warn"
    else:
        status = "ok"
    return {"ok": status != "critical", "status": status, "sections": sections}
