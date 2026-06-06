from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request

from app.api.routes import connectors_status
from app.core.auth import auth_from_request, has_action, load_auth_base_db, recent_login_events
from app.core.json_store import _pg_connect
from app.core.object_storage import ObjectStorageError, s3_enabled
from app.core.tenant_context import current_tenant_organization_id
from app.storage.relational_pim_store import (
    list_pim_channel_links,
    load_templates_db_doc,
    query_products_full,
)

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


def _dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso_age_minutes(value: Any) -> Optional[int]:
    raw = _text(value)
    if not raw:
        return None
    try:
        normalized = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() // 60))
    except Exception:
        return None


def _feature_value(feature: Dict[str, Any]) -> str:
    for key in ("value", "canonical_value", "resolved_value", "raw_value"):
        value = _text(feature.get(key))
        if value:
            return value
    values = feature.get("values")
    if isinstance(values, list):
        joined = ", ".join(_text(item) for item in values if _text(item))
        return joined.strip()
    return ""


def _has_source_evidence(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_source_evidence(item) for item in value.values()) or bool(value)
    if isinstance(value, list):
        return any(_has_source_evidence(item) for item in value) or bool(value)
    return bool(_text(value))


def _product_href(product_id: str, tab: str = "attributes") -> str:
    return f"/products/{product_id}?tab={tab}"


def _limited_append(rows: List[Dict[str, Any]], row: Dict[str, Any], limit: int = 24) -> None:
    if len(rows) < limit:
        rows.append(row)


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
              c.relname AS table_name,
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


def _lineage_section() -> Dict[str, Any]:
    products = query_products_full(limit=300)
    gaps: List[Dict[str, Any]] = []
    totals = {
        "products_sampled": len(products),
        "products_with_media": 0,
        "products_with_media_source": 0,
        "products_with_description_source": 0,
        "features_total": 0,
        "features_with_value": 0,
        "features_with_source": 0,
        "features_accepted": 0,
        "features_manual_required": 0,
        "features_without_source": 0,
    }
    for product in products:
        product_id = _text(product.get("id"))
        title = _text(product.get("title")) or product_id
        content = _dict(product.get("content"))
        source_values = _dict(content.get("source_values"))
        media = _list(content.get("media_images")) or _list(content.get("media"))
        if media:
            totals["products_with_media"] += 1
            if _has_source_evidence(source_values.get("media_images")):
                totals["products_with_media_source"] += 1
            else:
                _limited_append(gaps, {
                    "type": "media",
                    "title": title,
                    "product_id": product_id,
                    "issue": "У товара есть медиа, но не видно источника наполнения.",
                    "href": _product_href(product_id, "media"),
                })
        elif product_id:
            _limited_append(gaps, {
                "type": "media",
                "title": title,
                "product_id": product_id,
                "issue": "У товара нет медиа для выгрузки.",
                "href": _product_href(product_id, "media"),
            })
        if _has_source_evidence(source_values.get("descriptions")):
            totals["products_with_description_source"] += 1
        features = _list(product.get("feature_params")) or _list(product.get("selected_params"))
        for feature in features:
            if not isinstance(feature, dict):
                continue
            totals["features_total"] += 1
            value = _feature_value(feature)
            review_status = _text(feature.get("review_status"))
            has_source = _has_source_evidence(feature.get("source_values"))
            if value:
                totals["features_with_value"] += 1
            if has_source:
                totals["features_with_source"] += 1
            if review_status == "accepted":
                totals["features_accepted"] += 1
            if review_status == "manual_required":
                totals["features_manual_required"] += 1
            if value and not has_source and review_status != "accepted":
                totals["features_without_source"] += 1
                _limited_append(gaps, {
                    "type": "attribute",
                    "title": title,
                    "product_id": product_id,
                    "field": _text(feature.get("name")) or _text(feature.get("code")) or "Параметр",
                    "issue": "Значение заполнено без source_values и без принятой проверки.",
                    "href": _product_href(product_id, "attributes"),
                })
    warn_count = len(gaps) + int(totals["features_manual_required"])
    return _section(
        "warn" if warn_count else "ok",
        "Lineage данных",
        "Есть поля или медиа без понятного источника." if warn_count else "Источники данных видны на проверенной выборке.",
        totals=totals,
        items=gaps,
    )


def _review_queue_section() -> Dict[str, Any]:
    products = query_products_full(limit=300)
    items: List[Dict[str, Any]] = []
    counts = {
        "manual_required": 0,
        "source_conflicts": 0,
        "missing_media": 0,
        "failed_workflows": 0,
        "mapping_links_review": 0,
    }
    for product in products:
        product_id = _text(product.get("id"))
        title = _text(product.get("title")) or product_id
        content = _dict(product.get("content"))
        media = _list(content.get("media_images")) or _list(content.get("media"))
        if not media and product_id:
            counts["missing_media"] += 1
            _limited_append(items, {
                "type": "media",
                "title": title,
                "issue": "Нет медиа перед экспортом.",
                "href": _product_href(product_id, "media"),
            }, 30)
        for feature in _list(product.get("feature_params")) or _list(product.get("selected_params")):
            if not isinstance(feature, dict):
                continue
            review_status = _text(feature.get("review_status"))
            source_values = _dict(feature.get("source_values"))
            if review_status == "manual_required":
                counts["manual_required"] += 1
                _limited_append(items, {
                    "type": "attribute",
                    "title": title,
                    "field": _text(feature.get("name")) or _text(feature.get("code")) or "Параметр",
                    "issue": "Поле оставлено для ручной проверки.",
                    "href": _product_href(product_id, "attributes"),
                }, 30)
            if len(source_values.keys()) > 1 and not _feature_value(feature):
                counts["source_conflicts"] += 1
                _limited_append(items, {
                    "type": "attribute",
                    "title": title,
                    "field": _text(feature.get("name")) or _text(feature.get("code")) or "Параметр",
                    "issue": "Есть несколько источников, но нет выбранного значения.",
                    "href": _product_href(product_id, "attributes"),
                }, 30)
    org_id = current_tenant_organization_id()
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT workflow, run_id, status, updated_at, payload_json->>'error' AS error, payload_json->>'message' AS message
            FROM pim_workflow_runs
            WHERE organization_id = %s AND status = 'failed'
            ORDER BY updated_at DESC
            LIMIT 12
            """,
            [org_id],
        )
        failed = _extract_rows(cur)
    counts["failed_workflows"] = len(failed)
    for row in failed:
        _limited_append(items, {
            "type": "workflow",
            "title": WORKFLOW_LABELS.get(_text(row.get("workflow")), _text(row.get("workflow")) or "Workflow"),
            "issue": _text(row.get("message")) or _text(row.get("error")) or "Workflow завершился ошибкой.",
            "href": "/admin/status",
        }, 30)
    try:
        links = list_pim_channel_links(status="review", organization_id=org_id)
    except TypeError:
        links = []
    counts["mapping_links_review"] = len(links)
    for link in links[:8]:
        _limited_append(items, {
            "type": "mapping",
            "title": _text(link.get("title")) or _text(link.get("entity_id")) or "Связка",
            "issue": "Связка канала ожидает проверки.",
            "href": "/sources?tab=categories",
        }, 30)
    total = sum(int(v or 0) for v in counts.values())
    return _section(
        "warn" if total else "ok",
        "Очередь проверки",
        f"К проверке: {total}." if total else "Нет явной очереди ручной проверки.",
        totals=counts,
        items=items,
    )


def _export_targets_section() -> Dict[str, Any]:
    marketplace = _marketplace_section()
    providers = _list(marketplace.get("providers"))
    targets: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    totals = {"export_enabled": 0, "safe_test_enabled": 0, "stores": 0, "misconfigured": 0}
    for provider in providers:
        for store in _list(provider.get("stores")):
            if not isinstance(store, dict):
                continue
            totals["stores"] += 1
            row = {
                "provider": _text(provider.get("provider")),
                "provider_title": _text(provider.get("title")),
                "store_id": _text(store.get("store_id")),
                "title": _text(store.get("title")),
                "enabled": bool(store.get("enabled")),
                "export_enabled": bool(store.get("export_enabled")),
                "safe_test_enabled": bool(store.get("safe_test_enabled")),
                "last_check_status": _text(store.get("last_check_status")),
                "href": "/connectors/status?tab=marketplaces",
            }
            if row["export_enabled"]:
                totals["export_enabled"] += 1
                targets.append(row)
            if row["safe_test_enabled"]:
                totals["safe_test_enabled"] += 1
            if row["export_enabled"] and row["last_check_status"] == "error":
                totals["misconfigured"] += 1
                warnings.append({**row, "issue": "Магазин выбран для экспорта, но последняя проверка доступа упала."})
    status = "critical" if totals["misconfigured"] else "warn" if not totals["export_enabled"] else "ok"
    detail = "Выбранные магазины экспорта видны явно." if status == "ok" else "Нужно выбрать или проверить магазины экспорта."
    return _section(status, "Цели экспорта", detail, totals=totals, rows=targets, items=warnings)


def _ai_governance_section() -> Dict[str, Any]:
    org_id = current_tenant_organization_id()
    ai_workflows = [
        "marketplace_attribute_ai_match",
        "marketplace_value_ai_match",
        "marketplace_export_semantics_ai",
        "competitor_discovery",
    ]
    conn, _, _ = _pg_connect()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT workflow, status, COUNT(*)::int AS count, MAX(updated_at) AS latest_at
            FROM pim_workflow_runs
            WHERE organization_id = %s AND workflow = ANY(%s)
            GROUP BY workflow, status
            ORDER BY workflow, status
            """,
            [org_id, ai_workflows],
        )
        rows = _extract_rows(cur)
    memory = []
    try:
        memory = list_pim_channel_links(scope="ai_mapping_memory", organization_id=org_id, limit=500)  # type: ignore[arg-type]
    except TypeError:
        memory = list_pim_channel_links(scope="ai_mapping_memory", organization_id=org_id)
    totals = {
        "ai_runs": sum(int(row.get("count") or 0) for row in rows),
        "failed": sum(int(row.get("count") or 0) for row in rows if row.get("status") == "failed"),
        "queued_or_running": sum(int(row.get("count") or 0) for row in rows if row.get("status") in {"queued", "running"}),
        "learning_links": len(memory),
        "manual_review_enforced": True,
    }
    status = "critical" if totals["failed"] else "warn" if totals["queued_or_running"] else "ok"
    return _section(
        status,
        "AI governance",
        "AI-подборы пишутся в workflow и требуют проверки человеком.",
        labels=WORKFLOW_LABELS,
        summary=rows,
        totals=totals,
        items=[{
            "title": _text(item.get("title")) or _text(item.get("entity_id")) or "AI memory",
            "issue": "Пример обучения для будущего подбора кандидатов.",
            "href": "/sources?tab=params",
        } for item in memory[:10]],
    )


def _growth_controls_section() -> Dict[str, Any]:
    table_section = _table_size_section()
    rows = _list(table_section.get("rows"))
    conn, _, _ = _pg_connect()
    org_id = current_tenant_organization_id()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status, COUNT(*)::int AS count, MIN(updated_at) AS oldest_at, MAX(updated_at) AS latest_at
            FROM pim_workflow_runs
            WHERE organization_id = %s
            GROUP BY status
            ORDER BY status
            """,
            [org_id],
        )
        workflows = _extract_rows(cur)
        cur.execute(
            """
            SELECT path, octet_length(payload::text)::bigint AS payload_bytes, updated_at
            FROM json_documents
            ORDER BY octet_length(payload::text) DESC
            LIMIT 10
            """
        )
        json_docs = _extract_rows(cur)
    stale = []
    for row in workflows:
        if row.get("status") not in {"queued", "running"}:
            continue
        age = _iso_age_minutes(row.get("oldest_at"))
        if age is not None and age > 120:
            stale.append({**row, "age_minutes": age})
    largest = max([int(row.get("total_bytes") or 0) for row in rows] or [0])
    status = "warn" if stale or largest > 1024 * 1024 * 1024 else "ok"
    return _section(
        status,
        "Рост данных",
        "Есть stale workflow или крупные таблицы." if status == "warn" else "Критичного роста данных не видно.",
        rows=rows,
        recent=workflows,
        items=json_docs,
        totals={"largest_table_bytes": largest, "stale_workflows": len(stale), "json_documents_sampled": len(json_docs)},
    )


def _access_section() -> Dict[str, Any]:
    auth_db = load_auth_base_db()
    users = _dict(auth_db.get("users"))
    roles = _dict(auth_db.get("roles"))
    login_events = recent_login_events(30)
    failed_logins = [row for row in login_events if _text(row.get("status")) != "success"]
    inactive_users = [user for user in users.values() if isinstance(user, dict) and _text(user.get("status")) not in {"active", "invited"}]
    role_ids = set(roles.keys())
    users_without_role = []
    for user_id, user in users.items():
        if not isinstance(user, dict):
            continue
        user_roles = [_text(item) for item in _list(user.get("roles")) if _text(item)]
        if user_roles and not any(role in role_ids for role in user_roles):
            users_without_role.append({"user_id": user_id, "email": _text(user.get("email")), "roles": user_roles})
    status = "critical" if users_without_role else "warn" if failed_logins else "ok"
    return _section(
        status,
        "Доступ и роли",
        "Есть пользователи с невалидными ролями." if users_without_role else "Последние события входа и роли видны.",
        totals={
            "users": len(users),
            "roles": len(roles),
            "inactive_users": len(inactive_users),
            "failed_logins": len(failed_logins),
            "users_without_existing_role": len(users_without_role),
        },
        recent=login_events[:12],
        items=[{**row, "href": "/admin/access"} for row in users_without_role[:12]],
    )


def _info_model_versions_section() -> Dict[str, Any]:
    org_id = current_tenant_organization_id()
    templates_doc = load_templates_db_doc(org_id)
    templates = _dict(templates_doc.get("templates"))
    links = _dict(templates_doc.get("category_templates"))
    items: List[Dict[str, Any]] = []
    totals = {"templates": len(templates), "linked_categories": len(links), "with_history": 0, "without_history": 0, "draft": 0}
    for template_id, template in templates.items():
        if not isinstance(template, dict):
            continue
        meta = _dict(template.get("meta"))
        info_model = _dict(meta.get("info_model"))
        history = _list(meta.get("history")) or _list(info_model.get("history")) or _list(info_model.get("versions"))
        if history:
            totals["with_history"] += 1
        else:
            totals["without_history"] += 1
        if _text(info_model.get("status")) in {"draft", "review"} or bool(info_model.get("is_draft")):
            totals["draft"] += 1
        _limited_append(items, {
            "title": _text(template.get("name")) or _text(template_id),
            "issue": "Нет истории версий инфо-модели." if not history else f"Версий: {len(history)}.",
            "href": f"/templates/{template_id}",
        }, 18)
    status = "warn" if totals["without_history"] else "ok"
    return _section(
        status,
        "Версии инфо-моделей",
        "Часть инфо-моделей без истории версий." if status == "warn" else "История версий есть у всех инфо-моделей.",
        totals=totals,
        items=items,
    )


def _release_safety_section() -> Dict[str, Any]:
    required_checks = [
        {"title": "Python compile", "command": "PYTHONPATH=backend python3 -m compileall backend/app"},
        {"title": "Backend smoke", "command": "pytest backend/tests/test_api_read_smoke.py backend/tests/test_scenario_smoke.py -q"},
        {"title": "Frontend build", "command": "npm run build"},
        {"title": "Production smoke", "command": "python3 scripts/scenario_smoke.py --base-url https://pim.id-smart.ru --public-only --insecure-ssl"},
        {"title": "Git divergence", "command": "scripts/git_release_safety.sh"},
    ]
    return _section(
        "ok",
        "Release safety",
        "Чеклист релиза собран в одном месте; git-divergence проверяется отдельным скриптом.",
        items=required_checks,
        totals={"checks": len(required_checks)},
    )


def _auth_smoke_section() -> Dict[str, Any]:
    enabled = _text(os.getenv("SMARTPIM_AUTH_SMOKE")).lower() in {"1", "true", "yes", "on"}
    email_configured = bool(_text(os.getenv("SMARTPIM_SMOKE_EMAIL")))
    password_configured = bool(_text(os.getenv("SMARTPIM_SMOKE_PASSWORD")))
    product_flow_enabled = _text(os.getenv("SMARTPIM_SMOKE_PRODUCT_FLOW") or os.getenv("APP_SCENARIO_SMOKE_PRODUCT_FLOW")).lower() in {"1", "true", "yes", "on"}
    flow_category_configured = bool(_text(os.getenv("SMARTPIM_SMOKE_FLOW_CATEGORY_ID")))
    flow_product_configured = bool(_text(os.getenv("SMARTPIM_SMOKE_FLOW_PRODUCT_ID")))
    flow_sku_configured = bool(_text(os.getenv("SMARTPIM_SMOKE_FLOW_SKU_MARKER")))
    ready = enabled and email_configured and password_configured
    partial = enabled and not ready
    status = "ok" if ready else "critical" if partial else "warn"
    if ready:
        detail = "Authenticated deploy smoke включен и секреты заданы."
    elif partial:
        detail = "Authenticated deploy smoke включен, но не все секреты заданы."
    else:
        detail = "Authenticated deploy smoke выключен; публичный smoke остается активным."
    return _section(
        status,
        "Authenticated smoke",
        detail,
        totals={
            "enabled": enabled,
            "email_configured": email_configured,
            "password_configured": password_configured,
            "ready": ready,
            "product_flow_enabled": product_flow_enabled,
            "flow_category_configured": flow_category_configured,
            "flow_product_configured": flow_product_configured,
            "flow_sku_configured": flow_sku_configured,
        },
        items=[
            {
                "title": "SMARTPIM_AUTH_SMOKE",
                "issue": "Включает authenticated smoke в deploy." if enabled else "Выключен; deploy проверяет только публичные маршруты.",
                "status": "configured" if enabled else "disabled",
            },
            {
                "title": "SMARTPIM_SMOKE_EMAIL / SMARTPIM_SMOKE_PASSWORD",
                "issue": "Секреты заданы вне git." if email_configured and password_configured else "Нужно задать оба секрета на сервере/в окружении deploy.",
                "status": "configured" if email_configured and password_configured else "missing",
            },
            {
                "title": "SMARTPIM_SMOKE_PRODUCT_FLOW / APP_SCENARIO_SMOKE_PRODUCT_FLOW",
                "issue": "Полный browser-flow SKU включен." if product_flow_enabled else "Выключен; browser smoke проверяет только базовые маршруты.",
                "status": "configured" if product_flow_enabled else "disabled",
            },
            {
                "title": "SMARTPIM_SMOKE_FLOW_*",
                "issue": "Fixture category/product/SKU задан." if flow_category_configured and flow_product_configured and flow_sku_configured else "Можно оставить дефолтный product_70/50001 или явно задать category/product/SKU markers.",
                "status": "configured" if flow_category_configured and flow_product_configured and flow_sku_configured else "default",
            },
        ],
    )


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
        "export_targets": _safe_section(_export_targets_section),
        "workflows": _safe_section(_workflow_section),
        "lineage": _safe_section(_lineage_section),
        "review_queue": _safe_section(_review_queue_section),
        "ai_governance": _safe_section(_ai_governance_section),
        "growth_controls": _safe_section(_growth_controls_section),
        "access": _safe_section(_access_section),
        "info_model_versions": _safe_section(_info_model_versions_section),
        "release_safety": _safe_section(_release_safety_section),
        "auth_smoke": _safe_section(_auth_smoke_section),
        "table_sizes": _safe_section(_table_size_section),
    }
    if any(section.get("status") == "critical" for section in sections.values()):
        status = "critical"
    elif any(section.get("status") == "warn" for section in sections.values()):
        status = "warn"
    else:
        status = "ok"
    return {"ok": status != "critical", "status": status, "sections": sections}
