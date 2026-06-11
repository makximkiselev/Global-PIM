from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.ai_runtime import ai_enabled, require_ai_enabled
from app.core.json_store import read_doc, write_doc, with_lock
from app.core.tenant_context import current_tenant_organization_id
from app.core.value_mapping import normalize_value_key, provider_export_value_details
from app.storage.json_store import (
    ensure_global_attribute,
    load_dictionaries_db,
    load_dict,
    load_templates_db,
    new_id,
    save_dictionaries_db,
    save_dict,
    save_templates_db,
    slugify_code,
)
from app.storage.relational_pim_store import (
    claim_pim_workflow_run_as_running,
    get_pim_workflow_run,
    list_pim_workflow_runs,
    load_attribute_mapping_doc,
    load_attribute_value_refs_doc,
    load_catalog_nodes,
    load_category_mappings,
    query_products_full,
    save_attribute_value_refs_category_doc,
    save_attribute_mapping_doc,
    save_attribute_value_refs_doc,
    save_category_mappings,
    save_template_category_doc,
    upsert_pim_workflow_run,
)
from app.core.master_templates import (
    PARAM_GROUPS,
    base_field_by_code,
    base_field_by_name,
    base_template_fields,
    canonical_base_field_name,
    is_deprecated_template_code,
    is_deprecated_template_name,
    is_base_field_name,
    split_template_attrs,
)

router = APIRouter(prefix="/marketplaces/mapping", tags=["marketplace-mapping"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data"
MARKETPLACES_DIR = DATA_DIR / "marketplaces"
CACHE_DIR = MARKETPLACES_DIR / "_cache_v3"

MAPPINGS_PATH = MARKETPLACES_DIR / "category_mapping.json"
ATTR_MAPPING_PATH = MARKETPLACES_DIR / "attribute_master_mapping.json"
ATTR_VALUES_DICT_PATH = MARKETPLACES_DIR / "attribute_value_dictionary.json"
CATALOG_NODES_PATH = DATA_DIR / "catalog_nodes.json"
YANDEX_CATEGORY_PARAMS_PATH = MARKETPLACES_DIR / "yandex_market" / "category_parameters.json"
OZON_CATEGORY_ATTRS_PATH = MARKETPLACES_DIR / "ozon" / "category_attributes.json"
MAPPING_ISSUES_PATH = MARKETPLACES_DIR / "category_mapping_issues.json"
ATTR_FEEDBACK_PATH = MARKETPLACES_DIR / "attribute_match_feedback.json"
ATTR_DETAILS_CACHE_DIR = CACHE_DIR / "attr_details"

PROVIDER_TITLES: Dict[str, str] = {
    "yandex_market": "Я.Маркет",
    "ozon": "Ozon",
}

MAPPING_PROVIDERS: tuple[str, ...] = tuple(PROVIDER_TITLES.keys())

DEFAULT_SERVICE_NAMES: List[str] = [str(item["name"]) for item in base_template_fields()]
_ATTR_CATEGORIES_CACHE_TTL_SECONDS = float(os.getenv("ATTR_CATEGORIES_CACHE_TTL_SECONDS", "900") or "900")
_ATTR_DETAILS_CACHE_TTL_SECONDS = float(os.getenv("ATTR_DETAILS_CACHE_TTL_SECONDS", "900") or "900")
_ATTR_BOOTSTRAP_CACHE_TTL_SECONDS = float(os.getenv("ATTR_BOOTSTRAP_CACHE_TTL_SECONDS", "900") or "900")
_IMPORT_CATEGORIES_CACHE_TTL_SECONDS = float(os.getenv("IMPORT_CATEGORIES_CACHE_TTL_SECONDS", "900") or "900")
_VALUE_DETAILS_CACHE_TTL_SECONDS = float(os.getenv("VALUE_DETAILS_CACHE_TTL_SECONDS", "900") or "900")
_ATTR_DETAILS_CACHE_MAX_ITEMS = int(os.getenv("ATTR_DETAILS_CACHE_MAX_ITEMS", "8") or "8")
_VALUE_DETAILS_CACHE_MAX_ITEMS = int(os.getenv("VALUE_DETAILS_CACHE_MAX_ITEMS", "8") or "8")
_AI_MATCH_OLLAMA_TIMEOUT_SECONDS = float(os.getenv("AI_MATCH_OLLAMA_TIMEOUT_SECONDS", "90.0") or "90.0")
_AI_MATCH_OLLAMA_CHUNK_SIZE = int(os.getenv("AI_MATCH_OLLAMA_CHUNK_SIZE", "12") or "12")
_ATTR_DETAILS_CACHE_SCHEMA_VERSION = "v2"


def _ai_match_timeout_seconds() -> float:
    return max(_AI_MATCH_OLLAMA_TIMEOUT_SECONDS, 0.1)


def _ai_match_chunk_size() -> int:
    return max(_AI_MATCH_OLLAMA_CHUNK_SIZE, 1)


_import_categories_cache: Dict[str, Dict[str, Any]] = {}
_attr_categories_cache: Dict[str, Dict[str, Any]] = {}
_attr_details_cache: Dict[str, Dict[str, tuple[float, Dict[str, Any]]]] = {}
_attr_bootstrap_cache: Dict[str, Dict[str, Any]] = {}
_value_details_cache: Dict[str, Dict[str, tuple[float, Dict[str, Any]]]] = {}


def _current_org_cache_key() -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", current_tenant_organization_id()) or "default"


def _cache_entry(cache: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return cache.setdefault(_current_org_cache_key(), {"ts": 0.0, "payload": None})


def _details_cache_bucket() -> Dict[str, tuple[float, Dict[str, Any]]]:
    return _attr_details_cache.setdefault(_current_org_cache_key(), {})


def _value_details_cache_bucket() -> Dict[str, tuple[float, Dict[str, Any]]]:
    return _value_details_cache.setdefault(_current_org_cache_key(), {})


def _timed_cache_get(
    bucket: Dict[str, tuple[float, Dict[str, Any]]],
    key: str,
    ttl_seconds: float,
) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    cached = bucket.get(key)
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]
    if cached:
        bucket.pop(key, None)
    return None


def _timed_cache_set(
    bucket: Dict[str, tuple[float, Dict[str, Any]]],
    key: str,
    payload: Dict[str, Any],
    *,
    max_items: int,
    ttl_seconds: float,
) -> None:
    now = time.monotonic()
    for cached_key, cached_value in list(bucket.items()):
        if now - cached_value[0] >= ttl_seconds:
            bucket.pop(cached_key, None)
    bucket[key] = (now, payload)
    while len(bucket) > max(1, int(max_items)):
        oldest_key = min(bucket, key=lambda item_key: bucket[item_key][0])
        bucket.pop(oldest_key, None)


def _import_categories_cache_path() -> Path:
    return CACHE_DIR / f"import_categories_snapshot_{_current_org_cache_key()}.json"


def _attr_bootstrap_cache_path() -> Path:
    return CACHE_DIR / f"attr_bootstrap_snapshot_{_current_org_cache_key()}.json"


def _attr_categories_cache_path() -> Path:
    return CACHE_DIR / f"attr_categories_snapshot_{_current_org_cache_key()}.json"


def _invalidate_import_categories_cache() -> None:
    entry = _cache_entry(_import_categories_cache)
    entry["ts"] = 0.0
    entry["payload"] = None
    _persistent_cache_clear(_import_categories_cache_path())


def _attr_details_cache_path(catalog_category_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(catalog_category_id or "").strip()) or "unknown"
    return ATTR_DETAILS_CACHE_DIR / f"{_current_org_cache_key()}_{_ATTR_DETAILS_CACHE_SCHEMA_VERSION}_{safe}.json"


def _persistent_cache_read(path: Path, ttl_seconds: float) -> Optional[Dict[str, Any]]:
    doc = read_doc(path, default={"ts": 0.0, "payload": None})
    if not isinstance(doc, dict):
        return None
    ts = float(doc.get("ts") or 0.0)
    payload = doc.get("payload")
    if not payload:
        return None
    if time.time() - ts >= ttl_seconds:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _persistent_cache_write(path: Path, payload: Dict[str, Any]) -> None:
    write_doc(path, {"ts": time.time(), "payload": payload})


def _persistent_cache_clear(path: Path) -> None:
    write_doc(path, {"ts": 0.0, "payload": None})


def _persistent_attr_details_cache_clear_all() -> None:
    try:
        prefix = f"{_current_org_cache_key()}_"
        for child in ATTR_DETAILS_CACHE_DIR.glob(f"{prefix}*.json"):
            _persistent_cache_clear(child)
    except Exception:
        return


def warm_marketplace_mapping_read_models() -> Dict[str, Any]:
    warmed_details = 0
    categories_payload = mapping_import_categories()
    attr_categories_payload = mapping_attribute_categories()
    bootstrap_payload = mapping_attribute_bootstrap()
    items = attr_categories_payload.get("items") if isinstance(attr_categories_payload, dict) else []
    if isinstance(items, list):
        for item in items:
            cid = str((item or {}).get("id") or "").strip()
            if not cid:
                continue
            try:
                mapping_attribute_details(cid)
                warmed_details += 1
            except Exception:
                continue
    return {
        "ok": True,
        "categories": len(categories_payload.get("catalog_items") or []) if isinstance(categories_payload, dict) else 0,
        "mapped_categories": len(items or []) if isinstance(items, list) else 0,
        "bootstrap_count": int(bootstrap_payload.get("count") or 0) if isinstance(bootstrap_payload, dict) else 0,
        "details_warmed": warmed_details,
    }


def _load_catalog_nodes() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _catalog_rows(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        if not nid:
            continue
        by_id[nid] = n

    children_by_parent: Dict[str, List[str]] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        if not nid:
            continue
        children_by_parent.setdefault(pid, []).append(nid)

    def path_of(nid: str) -> str:
        parts: List[str] = []
        seen = set()
        cur = by_id.get(nid)
        while cur:
            cid = str(cur.get("id") or "")
            if not cid or cid in seen:
                break
            seen.add(cid)
            parts.append(str(cur.get("name") or cid))
            pid = str(cur.get("parent_id") or "").strip()
            cur = by_id.get(pid) if pid else None
        parts.reverse()
        return " / ".join(parts)

    out: List[Dict[str, Any]] = []
    for nid, n in by_id.items():
        out.append(
            {
                "id": nid,
                "name": str(n.get("name") or ""),
                "path": path_of(nid),
                "is_leaf": len(children_by_parent.get(nid, [])) == 0,
            }
        )
    out.sort(key=lambda x: (x.get("path") or "").lower())
    return out


def _provider_dir(provider: str) -> Path:
    return MARKETPLACES_DIR / provider


def _load_provider_categories(provider: str) -> List[Dict[str, Any]]:
    # SQL-only: do not rely on filesystem dirs/files existence.
    tree_path = _provider_dir(provider) / "categories_tree.json"
    doc = read_doc(tree_path, default={})
    flat = doc.get("flat") if isinstance(doc, dict) else []
    if not isinstance(flat, list):
        return []
    out: List[Dict[str, Any]] = []
    for x in flat:
        if not isinstance(x, dict):
            continue
        cid = str(x.get("id") or "").strip()
        if not cid:
            continue
        out.append(
            {
                "id": cid,
                "name": str(x.get("name") or ""),
                "path": str(x.get("path") or x.get("name") or cid),
                "is_leaf": bool(x.get("is_leaf", False)),
                "source_store_ids": [
                    str(item or "").strip()
                    for item in (x.get("source_store_ids") if isinstance(x.get("source_store_ids"), list) else [])
                    if str(item or "").strip()
                ],
                "source_titles": [
                    str(item or "").strip()
                    for item in (x.get("source_titles") if isinstance(x.get("source_titles"), list) else [])
                    if str(item or "").strip()
                ],
                "source_client_ids": [
                    str(item or "").strip()
                    for item in (x.get("source_client_ids") if isinstance(x.get("source_client_ids"), list) else [])
                    if str(item or "").strip()
                ],
                "attribute_validated_store_ids": [
                    str(item or "").strip()
                    for item in (x.get("attribute_validated_store_ids") if isinstance(x.get("attribute_validated_store_ids"), list) else [])
                    if str(item or "").strip()
                ],
                "attribute_validated_titles": [
                    str(item or "").strip()
                    for item in (x.get("attribute_validated_titles") if isinstance(x.get("attribute_validated_titles"), list) else [])
                    if str(item or "").strip()
                ],
                "attribute_validated_client_ids": [
                    str(item or "").strip()
                    for item in (x.get("attribute_validated_client_ids") if isinstance(x.get("attribute_validated_client_ids"), list) else [])
                    if str(item or "").strip()
                ],
            }
        )
    out.sort(key=lambda x: (x.get("path") or "").lower())
    return out


def _normalize_provider_category_lookup_id(provider: str, provider_category_id: str) -> str:
    pid = str(provider_category_id or "").strip()
    if not pid:
        return ""
    if provider == "ozon" and pid.startswith("type:"):
        parts = pid.split(":")
        if len(parts) >= 3:
            return str(parts[1] or "").strip()
    return pid


def _provider_category_name(provider: str, provider_category_id: str) -> str:
    pid = _normalize_provider_category_lookup_id(provider, provider_category_id)
    if not pid:
        return ""
    for item in _load_provider_categories(provider):
        if str(item.get("id") or "").strip() == pid:
            return str(item.get("path") or item.get("name") or pid)
    return ""


def _is_provider_category_known_or_validated(
    provider: str,
    provider_category_id: str,
    provider_items: List[Dict[str, Any]],
) -> bool:
    pid = str(provider_category_id or "").strip()
    if not pid:
        return True
    item_ids = {str(item.get("id") or "").strip() for item in provider_items if isinstance(item, dict)}
    if pid in item_ids:
        return True
    if provider != "ozon":
        return False
    lookup_id = _normalize_provider_category_lookup_id(provider, pid)
    for item in provider_items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        category_id = str(item.get("category_id") or "").strip()
        if lookup_id not in {item_id, category_id}:
            continue
        validated_titles = item.get("attribute_validated_titles")
        validated_ids = item.get("attribute_validated_client_ids")
        if (isinstance(validated_titles, list) and validated_titles) or (isinstance(validated_ids, list) and validated_ids):
            return True
    return False


def _load_mappings() -> Dict[str, Dict[str, str]]:
    items = load_category_mappings()
    out: Dict[str, Dict[str, str]] = {}
    for catalog_id, m in (items or {}).items():
        cid = str(catalog_id or "").strip()
        if not cid or not isinstance(m, dict):
            continue
        row: Dict[str, str] = {}
        for provider, provider_cat_id in m.items():
            p = str(provider or "").strip()
            pcid = str(provider_cat_id or "").strip()
            if p and pcid:
                row[p] = pcid
        if row:
            out[cid] = row
    return out


def _save_mappings(items: Dict[str, Dict[str, str]]) -> None:
    save_category_mappings(items)


def _catalog_parent_map(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    parent_by_id: Dict[str, str] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        if nid and pid:
            parent_by_id[nid] = pid
    return parent_by_id


def _effective_provider_category_id(
    catalog_category_id: str,
    provider: str,
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
) -> str:
    cid = str(catalog_category_id or "").strip()
    p = str(provider or "").strip()
    if not cid or not p:
        return ""
    direct_row = mappings.get(cid) or {}
    if isinstance(direct_row, dict):
        direct = str(direct_row.get(p) or "").strip()
        if direct:
            return direct
    seen: set[str] = set()
    cur = parent_by_id.get(cid, "")
    while cur and cur not in seen:
        seen.add(cur)
        row = mappings.get(cur) or {}
        if isinstance(row, dict):
            v = str(row.get(p) or "").strip()
            if v:
                return v
        cur = parent_by_id.get(cur, "")
    return ""


def _effective_mapping_for_catalog(
    catalog_category_id: str,
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    providers = list(PROVIDER_TITLES.keys())
    for p in providers:
        v = _effective_provider_category_id(catalog_category_id, p, mappings, parent_by_id)
        if v:
            out[p] = v
    return out


def _effective_mapping_sources_for_catalog(
    catalog_category_id: str,
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
) -> Dict[str, str]:
    cid = str(catalog_category_id or "").strip()
    out: Dict[str, str] = {}
    if not cid:
        return out
    for provider in PROVIDER_TITLES.keys():
        direct = str((mappings.get(cid) or {}).get(provider) or "").strip()
        if direct:
            out[provider] = cid
            continue
        source = _nearest_direct_ancestor(cid, provider, mappings, parent_by_id)
        if source:
            out[provider] = source
    return out


def _direct_mapping_for_catalog(
    catalog_category_id: str,
    mappings: Dict[str, Dict[str, str]],
) -> Dict[str, str]:
    cid = str(catalog_category_id or "").strip()
    row = mappings.get(cid) if cid else {}
    if not isinstance(row, dict):
        row = {}
    out: Dict[str, str] = {}
    for provider in MAPPING_PROVIDERS:
        value = str(row.get(provider) or "").strip()
        if value:
            out[provider] = value
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_attr_mapping_doc() -> Dict[str, Any]:
    doc = load_attribute_mapping_doc()
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    return doc


def _load_attr_values_dict_doc() -> Dict[str, Any]:
    doc = load_attribute_value_refs_doc()
    if not isinstance(doc, dict):
        doc = {"version": 2, "updated_at": None, "items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    if not isinstance(doc.get("version"), int) or int(doc.get("version") or 0) < 2:
        doc["version"] = 2
    return doc


def _save_attr_values_dict_doc(doc: Dict[str, Any]) -> None:
    doc["updated_at"] = _now_iso()
    save_attribute_value_refs_doc(doc)


def _unique_text_values(values: Any, limit: int = 500) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in _extract_text_list(values):
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _load_attr_feedback_doc() -> Dict[str, Any]:
    doc = read_doc(ATTR_FEEDBACK_PATH, default={"version": 1, "pair_feedback": {}, "name_feedback": {}})
    if not isinstance(doc, dict):
        doc = {"version": 1, "pair_feedback": {}, "name_feedback": {}}
    if not isinstance(doc.get("pair_feedback"), dict):
        doc["pair_feedback"] = {}
    if not isinstance(doc.get("name_feedback"), dict):
        doc["name_feedback"] = {}
    return doc


def _save_attr_feedback_doc(doc: Dict[str, Any]) -> None:
    write_doc(ATTR_FEEDBACK_PATH, doc)


def _upsert_attr_values_dictionary_for_category(
    catalog_category_id: str,
    rows: List[Dict[str, Any]],
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
) -> None:
    """
    Stores category-specific source dictionaries and bindings.
    Marketplace values are saved only as reference data and must not become
    canonical values of our template/dictionary.
    """
    cid = str(catalog_category_id or "").strip()
    if not cid:
        return
    cat_mapping = _effective_mapping_for_catalog(cid, mappings, parent_by_id)
    norm_rows = _normalize_attr_rows(rows)

    providers_payload: Dict[str, Dict[str, Any]] = {}
    for provider_code in MAPPING_PROVIDERS:
        provider_category_id = str((cat_mapping or {}).get(provider_code) or "").strip()
        params: Dict[str, Any] = {}
        for r in norm_rows:
            pmap = r.get("provider_map") if isinstance(r.get("provider_map"), dict) else {}
            pv = pmap.get(provider_code) if isinstance(pmap.get(provider_code), dict) else {}
            pid = str(pv.get("id") or "").strip()
            pname = str(pv.get("name") or "").strip()
            if not pid and not pname:
                continue
            key = pid or pname
            params[key] = {
                "provider_param_id": pid or None,
                "provider_param_name": pname or None,
                "catalog_name": str(r.get("catalog_name") or "").strip(),
                "group": str(r.get("group") or "").strip(),
                "kind": str(pv.get("kind") or "").strip(),
                "required": bool(pv.get("required") or False),
                "allowed_values": _unique_text_values(pv.get("values")),
                "export": bool(pv.get("export") or False),
                "confirmed": bool(r.get("confirmed") or False),
            }
        providers_payload[provider_code] = {
            "provider_category_id": provider_category_id or None,
            "parameters": params,
            "params_count": len(params),
        }

    by_catalog_name: Dict[str, Any] = {}
    for r in norm_rows:
        cname = str(r.get("catalog_name") or "").strip()
        if not cname:
            continue
        pmap = r.get("provider_map") if isinstance(r.get("provider_map"), dict) else {}
        kind_raw = ""
        for provider_code in MAPPING_PROVIDERS:
            cur_map = pmap.get(provider_code) if isinstance(pmap.get(provider_code), dict) else {}
            kind_raw = str(cur_map.get("kind") or "").strip()
            if kind_raw:
                break
        attr_type = _kind_to_template_type(kind_raw)
        attr_ref = ensure_global_attribute(
            title=cname,
            type_=attr_type,
            code=slugify_code(cname),
            scope="feature",
        )
        dict_id = str(attr_ref.get("dict_id") or "").strip()
        by_catalog_name[_norm_name(cname)] = {
            "catalog_name": cname,
            "group": str(r.get("group") or "").strip(),
            "attribute_id": str(attr_ref.get("id") or "").strip() or None,
            "dict_id": dict_id or None,
            "type": attr_type,
            "confirmed": bool(r.get("confirmed") or False),
            "bindings": r.get("provider_map") if isinstance(r.get("provider_map"), dict) else {},
        }

    payload = {
        "catalog_category_id": cid,
        "providers": providers_payload,
        "catalog_params": by_catalog_name,
        "rows_count": len(norm_rows),
        "updated_at": _now_iso(),
    }
    save_attribute_value_refs_category_doc(cid, payload)


def _catalog_param_group_locks() -> Dict[str, str]:
    """
    Lock map: catalog parameter title -> param_group from dictionaries store.
    Apply only for parameters with explicit type, as requested by product logic.
    """
    doc = load_dictionaries_db()
    items = doc.get("items") if isinstance(doc, dict) else []
    if not isinstance(items, list):
        return {}
    out: Dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        type_name = str(it.get("type") or "").strip()
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        group = str(meta.get("param_group") or "").strip()
        if not title or not type_name or group not in PARAM_GROUPS:
            continue
        out[_norm_name(title)] = group
    return out


def _apply_group_locks(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    locks = _catalog_param_group_locks()
    if not locks:
        return _normalize_attr_rows(rows)
    out: List[Dict[str, Any]] = []
    for r in _normalize_attr_rows(rows):
        name = _norm_name(str(r.get("catalog_name") or ""))
        locked_group = locks.get(name)
        if locked_group:
            r = {**r, "group": locked_group}
        out.append(r)
    return out


def _classify_param_group(catalog_name: str, yandex_name: str = "") -> str:
    s = " ".join([str(catalog_name or ""), str(yandex_name or "")]).lower()
    if any(x in s for x in ("описани", "аннотац", "annotation", "description")):
        return "Описание"
    if any(x in s for x in ("медиа", "картин", "изображ", "фото", "видеооблож", "video cover", "video", "видео")):
        return "Медиа"
    if any(x in s for x in ("sku", "штрихкод", "barcode", "партномер", "код продавца", "серийн")):
        return "Артикулы"
    if any(x in s for x in ("гарант", "срок службы", "service life", "страна производства", "страна происхождения", "страна сборки")):
        return "Гарантия"
    if any(
        x in s
        for x in (
            "вес",
            "ширина",
            "высота",
            "толщина",
            "размер",
            "длина кабеля",
            "упаков",
            "количество",
            "габарит",
        )
    ):
        return "Логистика"
    if any(x in s for x in ("rich", "видео", "хештег", "seo")):
        return "Прочее"
    return "О товаре"


def _normalize_param_group(group_value: Any, catalog_name: str, yandex_name: str = "") -> str:
    g = str(group_value or "").strip()
    if g in PARAM_GROUPS:
        return g
    return _classify_param_group(catalog_name, yandex_name)


def _provider_binding_payload(raw: Any) -> Dict[str, Any]:
    cur = raw if isinstance(raw, dict) else {}
    payload = {
        "id": str(cur.get("id") or "").strip(),
        "name": str(cur.get("name") or "").strip(),
        "kind": str(cur.get("kind") or "").strip(),
        "values": _extract_text_list(cur.get("values"))[:200],
        "required": bool(cur.get("required") or False),
        "export": bool(cur.get("export") or False),
    }
    match_source = str(cur.get("match_source") or cur.get("source") or "").strip()
    if match_source:
        payload["match_source"] = match_source
    try:
        match_confidence = float(cur.get("match_confidence"))
    except Exception:
        match_confidence = None
    if match_confidence is not None:
        payload["match_confidence"] = max(0.0, min(1.0, match_confidence))
    match_reason = str(cur.get("match_reason") or cur.get("reason") or "").strip()
    if match_reason:
        payload["match_reason"] = match_reason[:240]
    return payload


def _provider_binding_list(raw: Any) -> List[Dict[str, Any]]:
    cur = raw if isinstance(raw, dict) else {}
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: Any) -> None:
        payload = _provider_binding_payload(item)
        if not payload["id"] and not payload["name"]:
            return
        key = payload["id"] or f"name:{_norm_name(payload['name'])}"
        if key in seen:
            return
        seen.add(key)
        out.append(payload)

    _add(cur)
    bindings = cur.get("bindings") if isinstance(cur.get("bindings"), list) else []
    for item in bindings:
        _add(item)
    return out


def _provider_map_payload(raw: Any) -> Dict[str, Any]:
    payload = _provider_binding_payload(raw)
    payload["bindings"] = _provider_binding_list(raw)
    return payload


def _humanize_catalog_name(name_raw: Any) -> str:
    s = str(name_raw or "").strip()
    if not s:
        return ""
    direct_known = {
        "артикул": "Партномер",
        "артикул производителя": "Партномер",
        "изображение для миниатюры": "Картинки",
        "название группы вариантов": "Группа товара",
        "вес": "Вес упаковки, г",
        "ширина": "Ширина упаковки, мм",
        "высота": "Высота упаковки, мм",
        "длина": "Длина упаковки, мм",
        "глубина": "Длина упаковки, мм",
        "вес,г": "Вес упаковки, г",
        "вес, г": "Вес упаковки, г",
        "ширина,мм": "Ширина упаковки, мм",
        "ширина, мм": "Ширина упаковки, мм",
        "высота,мм": "Высота упаковки, мм",
        "высота, мм": "Высота упаковки, мм",
        "длина,мм": "Длина упаковки, мм",
        "длина, мм": "Длина упаковки, мм",
    }
    s_norm = " ".join(s.lower().replace("ё", "е").split())
    if s_norm in direct_known:
        return canonical_base_field_name(direct_known[s_norm])
    if not s.lower().startswith("dict_"):
        return canonical_base_field_name(s)
    key = s[5:].strip().lower()
    known = {
        "sku_gt": "SKU GT",
        "barcode": "Штрихкод",
        "штрихкод": "Штрихкод",
        "партномер": "Партномер",
        "артикул": "Партномер",
        "артикул_производителя": "Партномер",
        "изображение_для_миниатюры": "Картинки",
        "название_группы_вариантов": "Группа товара",
        "весг": "Вес упаковки, г",
        "ширинамм": "Ширина упаковки, мм",
        "высотамм": "Высота упаковки, мм",
        "длинамм": "Длина упаковки, мм",
        "наличие_серии": "Серия",
    }
    if key in known:
        return canonical_base_field_name(known[key])
    return canonical_base_field_name(key.replace("_", " ").strip().capitalize())


def _normalize_attr_rows(rows_in: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(rows_in, list):
        return out
    for x in rows_in:
        if not isinstance(x, dict):
            continue
        row_id = str(x.get("id") or "").strip() or str(uuid4())
        catalog_name = canonical_base_field_name(_humanize_catalog_name(x.get("catalog_name")))
        if is_deprecated_template_code(x.get("code")) or is_deprecated_template_name(catalog_name):
            continue
        confirmed = bool(x.get("confirmed") or False)
        pmap_in = x.get("provider_map") if isinstance(x.get("provider_map"), dict) else {}
        pmap: Dict[str, Dict[str, Any]] = {}
        for provider in MAPPING_PROVIDERS:
            cur = pmap_in.get(provider) if isinstance(pmap_in, dict) else None
            if not isinstance(cur, dict):
                pmap[provider] = _provider_map_payload({})
                continue
            pmap[provider] = _provider_map_payload(cur)
        if not catalog_name:
            for provider in MAPPING_PROVIDERS:
                catalog_name = canonical_base_field_name(str(pmap.get(provider, {}).get("name") or "").strip())
                if catalog_name:
                    break
        group_name = _normalize_param_group(
            x.get("group"),
            catalog_name,
            " ".join(str(pmap.get(provider, {}).get("name") or "") for provider in MAPPING_PROVIDERS).strip(),
        )
        out.append(
            {
                "id": row_id,
                "catalog_name": catalog_name,
                "group": group_name,
                "provider_map": pmap,
                "confirmed": confirmed,
            }
        )
    # Deduplicate rows by normalized catalog name (case/spacing-insensitive).
    # Keep first row as base and merge payload from duplicates.
    merged: Dict[str, Dict[str, Any]] = {}
    ordered_keys: List[str] = []
    for r in out:
        key = _norm_name(str(r.get("catalog_name") or ""))
        if not key:
            key = str(r.get("id") or "").strip() or str(uuid4())
        cur = merged.get(key)
        if not cur:
            merged[key] = r
            ordered_keys.append(key)
            continue

        cur_map = cur.get("provider_map") if isinstance(cur.get("provider_map"), dict) else {}
        row_map = r.get("provider_map") if isinstance(r.get("provider_map"), dict) else {}
        for provider in MAPPING_PROVIDERS:
            cur_payload = cur_map.get(provider) if isinstance(cur_map.get(provider), dict) else {}
            row_payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else {}
            cur_bindings = _provider_binding_list(cur_payload)
            row_bindings = _provider_binding_list(row_payload)
            if not cur_bindings and row_bindings:
                cur_map[provider] = _provider_map_payload(row_payload)
                cur["provider_map"] = cur_map
            elif cur_bindings and row_bindings:
                merged_provider = dict(cur_payload)
                merged_provider["bindings"] = [*cur_bindings, *row_bindings]
                cur_map[provider] = _provider_map_payload(merged_provider)
                cur["provider_map"] = cur_map
        cur["confirmed"] = bool(cur.get("confirmed") or r.get("confirmed"))
        if not str(cur.get("catalog_name") or "").strip() and str(r.get("catalog_name") or "").strip():
            cur["catalog_name"] = str(r.get("catalog_name") or "").strip()
        merged[key] = cur

    return [merged[k] for k in ordered_keys]


def _load_yandex_params(provider_category_id: str) -> List[Dict[str, Any]]:
    if not provider_category_id:
        return []
    doc = read_doc(YANDEX_CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return []
    row = items.get(str(provider_category_id))
    if not isinstance(row, dict):
        return []
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    result = raw.get("result") if isinstance(raw, dict) else {}
    params = result.get("parameters") if isinstance(result, dict) else []
    out: List[Dict[str, Any]] = []
    if isinstance(params, list):
        for p in params:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "").strip()
            name = str(p.get("name") or "").strip()
            if not pid and not name:
                continue
            kind = str(p.get("type") or "").strip()
            if bool(p.get("multivalue") or False):
                kind = f"{kind} (мульти)" if kind else "мульти"
            values: List[str] = []
            for key in ("values", "options", "enumValues", "suggestedValues"):
                vals = _extract_text_list(p.get(key))
                if vals:
                    values = vals[:120]
                    break
            out.append({
                "id": pid or name,
                "name": name or pid,
                "required": bool(p.get("required") or False),
                "kind": kind,
                "values": values,
            })
    return out


def _load_ozon_params(provider_category_id: str) -> List[Dict[str, Any]]:
    lookup_id = _normalize_provider_category_lookup_id("ozon", provider_category_id)
    if not lookup_id:
        return []
    doc = read_doc(OZON_CATEGORY_ATTRS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return []
    row = items.get(str(lookup_id))
    if not isinstance(row, dict):
        return []
    attrs = row.get("attributes") if isinstance(row.get("attributes"), list) else []
    out: List[Dict[str, Any]] = []
    for p in attrs:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        name = str(p.get("name") or p.get("attribute_name") or "").strip()
        if not pid and not name:
            continue
        kind = str(p.get("type") or p.get("value_type") or "").strip()
        values: List[str] = []
        for key in ("values", "dictionary", "options", "available_values"):
            vals = _extract_text_list(p.get(key))
            if vals:
                values = vals[:120]
                break
        out.append(
            {
                "id": pid or name,
                "name": name or pid,
                "required": bool(p.get("is_required") or p.get("required") or False),
                "kind": kind,
                "values": values,
            }
        )
    return out


def _param_signature(params: List[Dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in params:
        if not isinstance(row, dict):
            continue
        pid = str(row.get("id") or "").strip().lower()
        name = re.sub(r"\s+", " ", str(row.get("name") or "").strip().lower())
        kind = str(row.get("kind") or "").strip().lower()
        key = pid or name
        if key:
            out.add(f"{key}|{kind}")
    return out


def _load_mapping_review_issues() -> Dict[str, Any]:
    doc = read_doc(MAPPING_ISSUES_PATH, default={"version": 1, "items": {}})
    if not isinstance(doc, dict):
        return {"version": 1, "items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    return doc


def _save_mapping_review_issues(doc: Dict[str, Any]) -> None:
    doc["version"] = 1
    doc["updated_at"] = _now_iso()
    write_doc(MAPPING_ISSUES_PATH, doc)


def _issue_key(catalog_category_id: str, provider: str, issue_type: str) -> str:
    safe_category = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(catalog_category_id or "").strip()) or "unknown"
    safe_provider = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(provider or "").strip()) or "provider"
    safe_type = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(issue_type or "").strip()) or "issue"
    return f"{safe_category}:{safe_provider}:{safe_type}"


def _record_mapping_review_issue(
    *,
    catalog_category_id: str,
    provider: str,
    issue_type: str,
    title: str,
    text: str,
    old_provider_category_id: str = "",
    new_provider_category_id: str = "",
    changed_count: int = 0,
) -> None:
    doc = _load_mapping_review_issues()
    items = doc["items"]
    key = _issue_key(catalog_category_id, provider, issue_type)
    items[key] = {
        "id": key,
        "type": issue_type,
        "status": "open",
        "provider": provider,
        "provider_title": PROVIDER_TITLES.get(provider, provider),
        "catalog_category_id": catalog_category_id,
        "old_provider_category_id": old_provider_category_id or None,
        "new_provider_category_id": new_provider_category_id or None,
        "changed_count": int(changed_count or 0),
        "title": title,
        "text": text,
        "to": f"/sources-mapping?tab=params&category={catalog_category_id}",
        "updated_at": _now_iso(),
    }
    _save_mapping_review_issues(doc)


def _close_mapping_review_issue(catalog_category_id: str, provider: str, issue_type: str) -> None:
    doc = _load_mapping_review_issues()
    key = _issue_key(catalog_category_id, provider, issue_type)
    row = doc["items"].get(key)
    if isinstance(row, dict):
        row["status"] = "closed"
        row["closed_at"] = _now_iso()
        row["updated_at"] = _now_iso()
        _save_mapping_review_issues(doc)


def _audit_ozon_category_binding(catalog_category_id: str, provider_category_id: str) -> Optional[Dict[str, Any]]:
    cid = str(catalog_category_id or "").strip()
    provider_id = str(provider_category_id or "").strip()
    if not cid or not provider_id or provider_id.startswith("type:"):
        return None
    try:
        from app.api.routes import ozon_market

        resolved_type_ids = ozon_market._resolve_type_ids(provider_id)  # noqa: SLF001 - local route utility
    except Exception:
        resolved_type_ids = []
    if resolved_type_ids:
        return None
    return {
        "id": _issue_key(cid, "ozon", "category_needs_reselect"),
        "type": "category_needs_reselect",
        "status": "open",
        "provider": "ozon",
        "provider_title": PROVIDER_TITLES["ozon"],
        "catalog_category_id": cid,
        "provider_category_id": provider_id,
        "title": "Ozon-категория требует перевыбора",
        "text": "В привязке сохранена старая категория без типа Ozon. Нужно выбрать категорию Ozon заново, чтобы загрузить характеристики.",
        "to": f"/sources-mapping?tab=sources&category={cid}",
    }


def _load_provider_params_for_review(provider: str, provider_category_id: str) -> List[Dict[str, Any]]:
    if provider == "ozon":
        return _load_ozon_params(provider_category_id)
    if provider == "yandex_market":
        return _load_yandex_params(provider_category_id)
    return []


def _record_category_relink_param_review(
    *,
    catalog_category_id: str,
    provider: str,
    old_provider_category_id: str,
    new_provider_category_id: str,
) -> None:
    if not old_provider_category_id or not new_provider_category_id or old_provider_category_id == new_provider_category_id:
        return
    old_params = _load_provider_params_for_review(provider, old_provider_category_id)
    new_params = _load_provider_params_for_review(provider, new_provider_category_id)
    if not old_params and not new_params:
        _record_mapping_review_issue(
            catalog_category_id=catalog_category_id,
            provider=provider,
            issue_type="category_params_not_loaded",
            title=f"{PROVIDER_TITLES.get(provider, provider)}: нужно загрузить параметры",
            text="Категория перевыбрана, но параметры старой и новой категории еще не загружены. Запустите импорт характеристик и вернитесь к проверке.",
            old_provider_category_id=old_provider_category_id,
            new_provider_category_id=new_provider_category_id,
        )
        return
    if not new_params:
        _record_mapping_review_issue(
            catalog_category_id=catalog_category_id,
            provider=provider,
            issue_type="category_params_not_loaded",
            title=f"{PROVIDER_TITLES.get(provider, provider)}: параметры новой категории не загружены",
            text="Категория перевыбрана, но по новой категории еще нет параметров. После загрузки параметров система проверит, нужно ли пересопоставление.",
            old_provider_category_id=old_provider_category_id,
            new_provider_category_id=new_provider_category_id,
        )
        return

    old_sig = _param_signature(old_params)
    new_sig = _param_signature(new_params)
    diff_count = len(old_sig.symmetric_difference(new_sig))
    if diff_count <= 0:
        _close_mapping_review_issue(catalog_category_id, provider, "category_params_changed")
        _close_mapping_review_issue(catalog_category_id, provider, "category_params_not_loaded")
        return

    _record_mapping_review_issue(
        catalog_category_id=catalog_category_id,
        provider=provider,
        issue_type="category_params_changed",
        title=f"{PROVIDER_TITLES.get(provider, provider)}: изменился набор параметров",
        text="После перевыбора категории набор параметров отличается. Нужно проверить сопоставление параметров и значений перед выгрузкой.",
        old_provider_category_id=old_provider_category_id,
        new_provider_category_id=new_provider_category_id,
        changed_count=diff_count,
    )


def audit_category_mapping_issues(limit: int = 20) -> Dict[str, Any]:
    catalog_rows = _catalog_rows(_load_catalog_nodes())
    category_by_id = {str(row.get("id") or ""): row for row in catalog_rows}
    mappings = _load_mappings()
    issues: List[Dict[str, Any]] = []
    for catalog_id, row in mappings.items():
        if not isinstance(row, dict):
            continue
        ozon_issue = _audit_ozon_category_binding(catalog_id, str(row.get("ozon") or ""))
        if ozon_issue:
            cat = category_by_id.get(str(catalog_id))
            if isinstance(cat, dict):
                ozon_issue["category_name"] = str(cat.get("name") or "")
                ozon_issue["category_path"] = str(cat.get("path") or cat.get("name") or "")
            issues.append(ozon_issue)

    review_doc = _load_mapping_review_issues()
    for row in (review_doc.get("items") or {}).values():
        if not isinstance(row, dict) or str(row.get("status") or "open") != "open":
            continue
        cat = category_by_id.get(str(row.get("catalog_category_id") or ""))
        item = dict(row)
        if isinstance(cat, dict):
            item["category_name"] = str(cat.get("name") or "")
            item["category_path"] = str(cat.get("path") or cat.get("name") or "")
        issues.append(item)

    issues.sort(key=lambda item: (str(item.get("type") or ""), str(item.get("category_path") or item.get("title") or "")))
    max_items = max(0, int(limit or 0))
    return {"count": len(issues), "items": issues[:max_items]}


def _has_ozon_params_cached(provider_category_id: str) -> bool:
    lookup_id = _normalize_provider_category_lookup_id("ozon", provider_category_id)
    if not lookup_id:
        return False
    doc = read_doc(OZON_CATEGORY_ATTRS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return False
    return isinstance(items.get(str(lookup_id)), dict)


def _has_yandex_params_cached(provider_category_id: str) -> bool:
    if not provider_category_id:
        return False
    doc = read_doc(YANDEX_CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return False
    return isinstance(items.get(str(provider_category_id)), dict)


def _extract_text_list(values: Any) -> List[str]:
    out: List[str] = []
    if isinstance(values, list):
        for v in values:
            if isinstance(v, str):
                s = v.strip()
                if s:
                    out.append(s)
            elif isinstance(v, (int, float)):
                out.append(str(v))
            elif isinstance(v, dict):
                for key in ("value", "name", "title", "label"):
                    s = str(v.get(key) or "").strip()
                    if s:
                        out.append(s)
                        break
    return out


def _kind_to_template_type(kind_raw: str) -> str:
    k = str(kind_raw or "").strip().lower()
    if not k:
        return "text"
    if any(x in k for x in ("bool", "boolean", "да/нет")):
        return "bool"
    if any(x in k for x in ("int", "integer", "numeric", "number", "decimal", "float", "число")):
        return "number"
    if any(x in k for x in ("enum", "select", "список", "выбор")):
        return "select"
    return "text"


def _value_mode_from_type(type_raw: Any, allowed_values: Optional[List[str]] = None) -> str:
    kind = str(type_raw or "").strip().lower()
    if any(x in kind for x in ("bool", "boolean", "да/нет")):
        return "boolean"
    if any(x in kind for x in ("int", "integer", "numeric", "number", "decimal", "float", "число")):
        return "number"
    if any(x in kind for x in ("multi", "мульти")):
        return "multi"
    if any(x in kind for x in ("enum", "select", "dictionary", "list", "список", "выбор")):
        return "enum"
    if allowed_values:
        return "enum"
    return "text"


def _value_payload_with_descendant_refs(
    *,
    catalog_category_id: str,
    values_items: Dict[str, Any],
    children_by_parent: Dict[str, List[str]],
    catalog_by_id: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    cid = str(catalog_category_id or "").strip()
    merged: Dict[str, Any] = {
        "catalog_category_id": cid,
        "providers": {},
        "catalog_params": {},
        "rows_count": 0,
        "branch_sources": [],
    }
    for child_id in _descendant_ids(cid, children_by_parent):
        child_payload = values_items.get(child_id) if isinstance(values_items.get(child_id), dict) else {}
        child_params = child_payload.get("catalog_params") if isinstance(child_payload.get("catalog_params"), dict) else {}
        if not child_params:
            continue
        child_meta = catalog_by_id.get(child_id) or {}
        source = {
            "id": child_id,
            "name": child_meta.get("name") or child_id,
            "path": child_meta.get("path") or child_meta.get("name") or child_id,
        }
        merged["branch_sources"].append(source)
        merged["rows_count"] = int(merged.get("rows_count") or 0) + int(child_payload.get("rows_count") or len(child_params))
        for provider, provider_payload in (child_payload.get("providers") or {}).items():
            if isinstance(provider_payload, dict) and provider not in merged["providers"]:
                merged["providers"][provider] = provider_payload
        for key, raw in child_params.items():
            if not isinstance(raw, dict):
                continue
            next_raw = dict(raw)
            next_raw["source_category"] = source
            merged["catalog_params"][f"{child_id}:{key}"] = next_raw
    return merged


def _dictionary_value_samples(dict_doc: Dict[str, Any], limit: int = 4) -> tuple[int, List[str], List[str]]:
    raw_dict_values = dict_doc.get("items") if isinstance(dict_doc.get("items"), list) else []
    value_count = 0
    pim_sample: List[str] = []
    pim_values: List[str] = []
    for value_item in raw_dict_values:
        value = ""
        if isinstance(value_item, str):
            value = str(value_item or "").strip()
        elif isinstance(value_item, dict):
            value = str(value_item.get("value") or "").strip()
        if not value:
            continue
        value_count += 1
        if len(pim_sample) < limit:
            pim_sample.append(value)
        pim_values.append(value)
    return value_count, pim_sample, pim_values


def _provider_value_coverage(dict_id: str, provider: str, pim_values: List[str], *, limit: int = 80) -> Dict[str, Any]:
    missing: List[str] = []
    covered = 0
    for value in pim_values:
        details = provider_export_value_details(dict_id, provider, value)
        output_value = str(details.get("value") or "").strip()
        if output_value and bool(details.get("mapped", True)):
            covered += 1
        else:
            missing.append(value)
    return {
        "covered_count": covered,
        "missing_count": len(missing),
        "missing_sample": missing[:4],
        "missing_values": missing[:limit],
    }


def _feature_source_evidence(
    *,
    category_ids: List[str],
    catalog_name: str,
    pim_values: List[str],
    limit: int = 12,
) -> List[Dict[str, Any]]:
    wanted_name = _norm_name(catalog_name)
    wanted_values = {normalize_value_key(value) for value in pim_values if normalize_value_key(value)}
    if not category_ids or not wanted_name:
        return []
    try:
        products = query_products_full(category_ids=category_ids, limit=220)
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for product in products:
        if not isinstance(product, dict):
            continue
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        features = content.get("features") if isinstance(content.get("features"), list) else []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            feature_name = _norm_name(feature.get("name") or feature.get("code"))
            value = str(feature.get("value") or feature.get("values") or "").strip()
            if feature_name != wanted_name and normalize_value_key(value) not in wanted_values:
                continue
            source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
            for source_group, group_payload in source_values.items():
                if not isinstance(group_payload, dict):
                    continue
                for source_id, payload in group_payload.items():
                    if not isinstance(payload, dict):
                        continue
                    raw_value = str(payload.get("raw_value") or payload.get("value") or "").strip()
                    resolved_value = str(payload.get("resolved_value") or payload.get("canonical_value") or raw_value).strip()
                    canonical_value = str(payload.get("canonical_value") or resolved_value).strip()
                    if not raw_value and not resolved_value and not canonical_value:
                        continue
                    key = "|".join([
                        str(product.get("id") or ""),
                        str(source_id or ""),
                        raw_value,
                        resolved_value,
                        canonical_value,
                    ])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(
                        {
                            "product_id": str(product.get("id") or "").strip(),
                            "sku_gt": str(product.get("sku_gt") or "").strip(),
                            "product_title": str(product.get("title") or product.get("name") or "").strip(),
                            "source_group": str(source_group or "").strip(),
                            "source_id": str(source_id or "").strip(),
                            "source_label": PROVIDER_TITLES.get(str(source_id or "").strip(), str(source_id or "").strip()),
                            "raw_value": raw_value,
                            "resolved_value": resolved_value,
                            "canonical_value": canonical_value,
                        }
                    )
                    if len(out) >= limit:
                        return out
    return out


def _provider_dictionary_quality(allowed_values: List[str], pim_value_count: int) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    count = len(allowed_values)
    sample_text = " ".join(allowed_values[:8]).lower()
    if count >= 80:
        issues.append({"code": "wide_dictionary", "label": "широкий справочник", "text": f"У площадки {count} значений; проверьте, что поле выбрано верно."})
    if pim_value_count == 0 and count >= 20:
        issues.append({"code": "no_pim_values", "label": "нет PIM значений", "text": "Справочник площадки есть, но PIM-словарь пуст."})
    if any(token in sample_text for token in ("#1 ", "#365", "bestselling", "чек-лист", "организуй")):
        issues.append({"code": "noisy_values", "label": "подозрительные значения", "text": "Первые значения похожи на чужой широкий справочник."})
    return {
        "status": "warn" if issues else "ok",
        "issues": issues,
    }


def _dictionary_values(doc: Dict[str, Any], limit: int = 80) -> List[str]:
    _, _, values = _dictionary_value_samples(doc, limit=limit)
    return values[:limit]


def _provider_allowed_values(doc: Dict[str, Any], provider: str, limit: int = 160) -> List[str]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    source_ref = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
    ref = source_ref.get(provider) if isinstance(source_ref.get(provider), dict) else {}
    return _unique_text_values(ref.get("allowed_values") or ref.get("values"), limit=limit)


def _provider_allowed_values_for_category_dict(catalog_category_id: str, dict_id: str, provider: str, limit: int = 160) -> List[str]:
    values_doc = _load_attr_values_dict_doc()
    items = values_doc.get("items") if isinstance(values_doc.get("items"), dict) else {}
    payload = items.get(catalog_category_id) if isinstance(items, dict) and isinstance(items.get(catalog_category_id), dict) else {}
    catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
    for raw in catalog_params.values():
        if not isinstance(raw, dict) or str(raw.get("dict_id") or "").strip() != dict_id:
            continue
        bindings = raw.get("bindings") if isinstance(raw.get("bindings"), dict) else {}
        ref = bindings.get(provider) if isinstance(bindings.get(provider), dict) else {}
        allowed = _unique_text_values(ref.get("allowed_values") or ref.get("values"), limit=limit)
        if allowed:
            return allowed
    return []


def _current_export_map(doc: Dict[str, Any], provider: str) -> Dict[str, str]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
    provider_map = export_map.get(provider) if isinstance(export_map.get(provider), dict) else {}
    out: Dict[str, str] = {}
    for key, value in provider_map.items():
        nkey = str(key or "").strip()
        nval = str(value or "").strip()
        if nkey and nval:
            out[nkey] = nval
    return out


def _mapped_export_value_is_allowed(output_value: str, allowed_values: List[str]) -> bool:
    value = str(output_value or "").strip()
    if not value:
        return False
    if not allowed_values:
        return True
    allowed_keys = {normalize_value_key(allowed) for allowed in allowed_values if normalize_value_key(allowed)}
    return normalize_value_key(value) in allowed_keys


def _score_value_pair(pim_value: str, allowed_value: str) -> float:
    pim = _norm_name(pim_value)
    allowed = _norm_name(allowed_value)
    if not pim or not allowed:
        return 0.0
    if pim == allowed:
        return 1.0
    pim_tokens = set(pim.split())
    allowed_tokens = set(allowed.split())
    overlap = len(pim_tokens & allowed_tokens) / max(len(pim_tokens | allowed_tokens), 1)
    containment = 0.0
    if len(pim) >= 3 and pim in allowed:
        containment = len(pim) / max(len(allowed), 1)
    elif len(allowed) >= 3 and allowed in pim:
        containment = len(allowed) / max(len(pim), 1)
    return max(overlap, containment * 0.9)


def _deterministic_value_suggestions(pim_values: List[str], allowed_values: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pim_value in pim_values:
        ranked = sorted(
            (
                (_score_value_pair(pim_value, allowed_value), allowed_value)
                for allowed_value in allowed_values
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        score, best = ranked[0] if ranked else (0.0, "")
        if score >= 0.92 and best:
            out.append(
                {
                    "canonical": pim_value,
                    "output": best,
                    "confidence": round(float(score), 3),
                    "source": "rule",
                    "reason": "exact_or_near_match",
                }
            )
    return out


async def _ollama_suggest_value_pairs(
    *,
    dict_title: str,
    provider: str,
    pim_values: List[str],
    allowed_values: List[str],
) -> List[Dict[str, Any]]:
    if not pim_values or not allowed_values:
        return []
    base_url = str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    model = str(os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")).strip() or "qwen2.5:7b-instruct"
    prompt = (
        "Верни только JSON без markdown: "
        "{\"pairs\":[{\"canonical\":\"PIM value\",\"output\":\"allowed value\",\"confidence\":0.0,\"reason\":\"short\"}]}. "
        "Сопоставь значения PIM со значениями маркетплейса только если это одно и то же значение. "
        "output обязан быть дословно одним из allowed values. Если не уверен, не возвращай пару. "
        f"Параметр: {str(dict_title or '')[:120]}. "
        f"Площадка: {provider}. "
        f"PIM values: {json.dumps(pim_values[:80], ensure_ascii=False)}. "
        f"Allowed values: {json.dumps(allowed_values[:160], ensure_ascii=False)}."
    )
    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {
            "temperature": 0.0,
            "top_p": 0.8,
            "num_ctx": 4096,
            "num_predict": 700,
        },
        "prompt": prompt,
    }
    timeout_budget = _ai_match_timeout_seconds()
    timeout = httpx.Timeout(timeout_budget, connect=min(max(timeout_budget / 2.0, 0.1), 3.0))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/api/generate", json=body)
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OLLAMA_HTTP_{response.status_code}")
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    obj = _json_extract(str((data or {}).get("response") or ""))
    pairs = obj.get("pairs") if isinstance(obj, dict) else None
    if not isinstance(pairs, list):
        return []
    return [pair for pair in pairs if isinstance(pair, dict)]


def _validated_value_suggestions(
    *,
    raw_pairs: List[Dict[str, Any]],
    pim_values: List[str],
    allowed_values: List[str],
    source: str,
) -> List[Dict[str, Any]]:
    pim_by_key = {normalize_value_key(value): value for value in pim_values if normalize_value_key(value)}
    allowed_by_key = {normalize_value_key(value): value for value in allowed_values if normalize_value_key(value)}
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for pair in raw_pairs:
        canonical = str(pair.get("canonical") or pair.get("pim") or pair.get("value") or "").strip()
        output = str(pair.get("output") or pair.get("provider") or pair.get("marketplace") or "").strip()
        canonical = pim_by_key.get(normalize_value_key(canonical), canonical if canonical in pim_values else "")
        output = allowed_by_key.get(normalize_value_key(output), output if output in allowed_values else "")
        if not canonical or not output:
            continue
        key = normalize_value_key(canonical)
        if key in seen:
            continue
        seen.add(key)
        try:
            confidence = float(pair.get("confidence") or 0.0)
        except Exception:
            confidence = 0.0
        out.append(
            {
                "canonical": canonical,
                "output": output,
                "confidence": max(0.0, min(confidence, 1.0)),
                "source": source,
                "reason": str(pair.get("reason") or source).strip()[:160],
            }
        )
    return out


def _apply_value_suggestions_to_dict(doc: Dict[str, Any], provider: str, suggestions: List[Dict[str, Any]]) -> Dict[str, Any]:
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
    provider_map = export_map.get(provider) if isinstance(export_map.get(provider), dict) else {}
    ai_meta = meta.get("value_ai") if isinstance(meta.get("value_ai"), dict) else {}
    provider_ai = ai_meta.get(provider) if isinstance(ai_meta.get(provider), dict) else {}
    applied = 0
    for suggestion in suggestions:
        key = str(suggestion.get("canonical") or "").strip()
        output = str(suggestion.get("output") or "").strip()
        if not key or not output:
            continue
        nkey = normalize_value_key(key)
        provider_map[nkey] = output
        provider_ai[nkey] = {
            "output": output,
            "confidence": suggestion.get("confidence"),
            "source": suggestion.get("source"),
            "reason": suggestion.get("reason"),
            "updated_at": _now_iso(),
        }
        applied += 1
    if applied:
        export_map[provider] = provider_map
        ai_meta[provider] = provider_ai
        meta["export_map"] = export_map
        meta["value_ai"] = ai_meta
        doc["meta"] = meta
        doc["updated_at"] = _now_iso()
        save_dict(doc)
    return doc


def _is_service_catalog_name(name_raw: Any) -> bool:
    target = _norm_name(str(name_raw or ""))
    if not target:
        return False
    return any(_norm_name(name) == target for name in _service_names())


def _row_required(row: Dict[str, Any]) -> bool:
    base_def = base_field_by_name(row.get("catalog_name"))
    if base_def:
        return bool(base_def.get("required"))
    pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    for provider in MAPPING_PROVIDERS:
        cur = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
        if bool(cur.get("required") or False):
            return True
    return False


def _template_scope_from_global(scope_raw: Any) -> str:
    scope = str(scope_raw or "").strip().lower()
    return "variant" if scope == "variant" else "common"


def _provider_binding_snapshot(provider_map: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for provider in MAPPING_PROVIDERS:
        cur = provider_map.get(provider) if isinstance(provider_map.get(provider), dict) else {}
        pid = str(cur.get("id") or "").strip()
        pname = str(cur.get("name") or "").strip()
        if not pid and not pname:
            continue
        out[provider] = {
            "id": pid or None,
            "name": pname or None,
            "kind": str(cur.get("kind") or "").strip() or None,
            "required": bool(cur.get("required") or False),
            "export": bool(cur.get("export") or False),
            "allowed_values": _unique_text_values(cur.get("values"), limit=200),
            "bindings": [
                {
                    "id": str(item.get("id") or "").strip() or None,
                    "name": str(item.get("name") or "").strip() or None,
                    "kind": str(item.get("kind") or "").strip() or None,
                    "required": bool(item.get("required") or False),
                    "export": bool(item.get("export") or False),
                    "allowed_values": _unique_text_values(item.get("values"), limit=200),
                }
                for item in _provider_binding_list(cur)
            ],
        }
    return out


def _ensure_dictionary_meta(dict_id: str, group: str, source_bindings: Dict[str, Any]) -> None:
    did = str(dict_id or "").strip()
    if not did:
        return
    doc = load_dict(did)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    changed = False
    base_def = None
    title = str(doc.get("title") or "").strip()
    code = str(doc.get("code") or "").strip()
    if title:
        base_def = base_field_by_name(title)
    if not base_def and code:
        base_def = base_field_by_code(code)

    group_name = str(group or "").strip()
    if group_name and group_name in PARAM_GROUPS and not str(meta.get("param_group") or "").strip():
        meta["param_group"] = group_name
        changed = True

    if base_def:
        if not bool(meta.get("service")):
            meta["service"] = True
            changed = True
        if bool(meta.get("required")) != bool(base_def.get("required")):
            meta["required"] = bool(base_def.get("required"))
            changed = True
        if str(meta.get("template_layer") or "").strip() != "base":
            meta["template_layer"] = "base"
            changed = True

    source_ref = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
    for provider, payload in (source_bindings or {}).items():
        next_payload = {
            "id": payload.get("id"),
            "name": payload.get("name"),
            "kind": payload.get("kind"),
            "required": bool(payload.get("required") or False),
            "allowed_values": _unique_text_values(payload.get("allowed_values"), limit=200),
        }
        if source_ref.get(provider) != next_payload:
            source_ref[provider] = next_payload
            changed = True

    if changed:
        meta["source_reference"] = source_ref
        doc["meta"] = meta
        save_dict(doc)


def _row_to_template_attr(row: Dict[str, Any], position: int, existing: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    name = canonical_base_field_name(row.get("catalog_name"))
    if not name:
        return None
    pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    kind = ""
    for provider in MAPPING_PROVIDERS:
        payload = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
        kind = str(payload.get("kind") or "").strip()
        if kind:
            break
    attr_type = _kind_to_template_type(kind)
    base_def = base_field_by_name(name) or base_field_by_code(slugify_code(name))
    if base_def:
        attr_type = str(base_def.get("type") or attr_type or "text")
    global_attr = ensure_global_attribute(
        title=name,
        type_=attr_type,
        code=slugify_code(name),
        scope="variant" if base_def and str(base_def.get("scope") or "") == "variant" else "feature",
    )
    dict_id = str(global_attr.get("dict_id") or "").strip()
    source_bindings = _provider_binding_snapshot(pmap)
    _ensure_dictionary_meta(dict_id, str(row.get("group") or "").strip(), source_bindings)

    base_options = existing.get("options") if isinstance(existing, dict) and isinstance(existing.get("options"), dict) else {}
    options: Dict[str, Any] = {**base_options}
    options.pop("values", None)
    options["dict_id"] = dict_id or None
    options["attribute_id"] = str(global_attr.get("id") or "").strip() or None
    options["param_group"] = str((base_def or {}).get("param_group") or row.get("group") or "").strip() or None
    options["layer"] = "base" if base_def else "category"
    if base_def:
        options["system_key"] = str(base_def.get("key") or "").strip() or None
    if source_bindings:
        options["source_bindings"] = source_bindings
    else:
        options.pop("source_bindings", None)

    return {
        "id": str((existing or {}).get("id") or new_id()),
        "name": name,
        "code": str((existing or {}).get("code") or slugify_code(name)),
        "type": attr_type,
        "required": bool((existing or {}).get("required") or _row_required(row) or bool((base_def or {}).get("required"))),
        "scope": "variant" if base_def and str(base_def.get("scope") or "") == "variant" else _template_scope_from_global(global_attr.get("scope")),
        "attribute_id": str(global_attr.get("id") or "").strip() or None,
        "options": options,
        "position": int(position),
        "locked": bool((existing or {}).get("locked") or bool(base_def) or _is_service_catalog_name(name)),
    }


def _migrate_mapping_documents_to_canonical_names() -> None:
    changed_attr_mapping = False
    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if isinstance(items, dict):
        for cid, payload in list(items.items()):
            if not isinstance(payload, dict):
                continue
            rows_before = payload.get("rows")
            rows_after = _normalize_attr_rows(rows_before)
            if rows_before != rows_after:
                payload["rows"] = rows_after
                payload["updated_at"] = _now_iso()
                items[cid] = payload
                changed_attr_mapping = True
    if changed_attr_mapping:
        doc["items"] = items
        save_attribute_mapping_doc(doc)

    changed_values = False
    values_doc = _load_attr_values_dict_doc()
    value_items = values_doc.get("items") if isinstance(values_doc.get("items"), dict) else {}
    if isinstance(value_items, dict):
        for cid, payload in list(value_items.items()):
            if not isinstance(payload, dict):
                continue
            catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
            merged_params: Dict[str, Any] = {}
            for _, raw in catalog_params.items():
                if not isinstance(raw, dict):
                    continue
                cname = canonical_base_field_name(raw.get("catalog_name"))
                key = _norm_name(cname)
                cur = merged_params.get(key)
                next_item = {
                    **raw,
                    "catalog_name": cname,
                }
                if not cur:
                    merged_params[key] = next_item
                    continue
                cur_bindings = cur.get("bindings") if isinstance(cur.get("bindings"), dict) else {}
                next_bindings = next_item.get("bindings") if isinstance(next_item.get("bindings"), dict) else {}
                has_cur_binding = any(
                    str(((cur_bindings.get(provider) if isinstance(cur_bindings.get(provider), dict) else {}).get("id") or "")).strip()
                    for provider in MAPPING_PROVIDERS
                )
                has_next_binding = any(
                    str(((next_bindings.get(provider) if isinstance(next_bindings.get(provider), dict) else {}).get("id") or "")).strip()
                    for provider in MAPPING_PROVIDERS
                )
                if not has_cur_binding and has_next_binding:
                    cur["bindings"] = next_bindings
                cur["confirmed"] = bool(cur.get("confirmed") or next_item.get("confirmed"))
                cur["attribute_id"] = str(cur.get("attribute_id") or next_item.get("attribute_id") or "").strip() or None
                cur["dict_id"] = str(cur.get("dict_id") or next_item.get("dict_id") or "").strip() or None
                merged_params[key] = cur
            normalized_catalog_params = {str(v.get("catalog_name") or ""): v for v in merged_params.values()}
            if catalog_params != normalized_catalog_params:
                payload["catalog_params"] = normalized_catalog_params
                value_items[cid] = payload
                changed_values = True
    if changed_values:
        values_doc["items"] = value_items
        _save_attr_values_dict_doc(values_doc)

    db = load_templates_db()
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    attrs_by_tpl = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    changed_templates = False
    if isinstance(attrs_by_tpl, dict):
        for tid, attrs in list(attrs_by_tpl.items()):
            if not isinstance(attrs, list):
                continue
            next_attrs: List[Dict[str, Any]] = []
            for attr in attrs:
                if not isinstance(attr, dict):
                    continue
                next_attr = dict(attr)
                canonical_name = canonical_base_field_name(next_attr.get("name"), next_attr.get("code"))
                if canonical_name != str(next_attr.get("name") or "").strip():
                    next_attr["name"] = canonical_name
                    changed_templates = True
                base_def = base_field_by_code(next_attr.get("code")) or base_field_by_name(canonical_name)
                options = next_attr.get("options") if isinstance(next_attr.get("options"), dict) else {}
                next_options = dict(options)
                if base_def:
                    if str(next_options.get("layer") or "").strip() != "base":
                        next_options["layer"] = "base"
                        changed_templates = True
                    if str(next_options.get("system_key") or "").strip() != str(base_def.get("key") or "").strip():
                        next_options["system_key"] = str(base_def.get("key") or "").strip() or None
                        changed_templates = True
                    if str(next_options.get("param_group") or "").strip() != str(base_def.get("param_group") or "").strip():
                        next_options["param_group"] = str(base_def.get("param_group") or "").strip() or None
                        changed_templates = True
                if next_options != options:
                    next_attr["options"] = next_options
                next_attrs.append(next_attr)
            attrs_by_tpl[tid] = next_attrs
        db["attributes"] = attrs_by_tpl
    if changed_templates:
        db["templates"] = templates
        save_templates_db(db)

    dict_db = load_dictionaries_db()
    dict_items = dict_db.get("items") if isinstance(dict_db.get("items"), list) else []
    changed_dicts = False
    for idx, item in enumerate(dict_items):
        if not isinstance(item, dict):
            continue
        base_def = base_field_by_code(item.get("code")) or base_field_by_name(item.get("title"))
        if not base_def:
            continue
        next_item = dict(item)
        canonical_title = str(base_def.get("name") or "").strip()
        if canonical_title and canonical_title != str(next_item.get("title") or "").strip():
            next_item["title"] = canonical_title
            changed_dicts = True
        meta = next_item.get("meta") if isinstance(next_item.get("meta"), dict) else {}
        next_meta = dict(meta)
        if str(next_meta.get("param_group") or "").strip() != str(base_def.get("param_group") or "").strip():
            next_meta["param_group"] = str(base_def.get("param_group") or "").strip()
            changed_dicts = True
        if str(next_meta.get("template_layer") or "").strip() != "base":
            next_meta["template_layer"] = "base"
            changed_dicts = True
        if bool(next_meta.get("service")) is not True:
            next_meta["service"] = True
            changed_dicts = True
        if bool(next_meta.get("required")) != bool(base_def.get("required")):
            next_meta["required"] = bool(base_def.get("required"))
            changed_dicts = True
        if next_meta != meta:
            next_item["meta"] = next_meta
        dict_items[idx] = next_item
    if changed_dicts:
        dict_db["items"] = dict_items
        save_dictionaries_db(dict_db)


def _upsert_template_from_attr_mapping(
    category_id: str,
    rows: List[Dict[str, Any]],
    category_name: str = "",
    mappings: Optional[Dict[str, Dict[str, str]]] = None,
    parent_by_id: Optional[Dict[str, str]] = None,
) -> None:
    cid = str(category_id or "").strip()
    if not cid:
        return
    norm_rows = _normalize_attr_rows(rows)
    mappings = mappings if isinstance(mappings, dict) else _load_mappings()
    parent_by_id = parent_by_id if isinstance(parent_by_id, dict) else _catalog_parent_map(_load_catalog_nodes())
    effective_yandex_category_id = _effective_provider_category_id(cid, "yandex_market", mappings, parent_by_id)
    effective_yandex_category_name = _provider_category_name("yandex_market", effective_yandex_category_id)
    yandex_params = _load_yandex_params(effective_yandex_category_id)
    yandex_required_count = sum(1 for item in yandex_params if bool(item.get("required") or False))

    db = load_templates_db()
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    attrs_by_tpl = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    cat_to_tpls = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    if not isinstance(templates, dict):
        templates = {}
    if not isinstance(attrs_by_tpl, dict):
        attrs_by_tpl = {}
    if not isinstance(cat_to_tpls, dict):
        cat_to_tpls = {}

    tids = cat_to_tpls.get(cid) if isinstance(cat_to_tpls.get(cid), list) else []
    tids = [str(t or "").strip() for t in (tids or []) if str(t or "").strip()]

    template_id = tids[0] if tids else ""
    template_record = templates.get(template_id) if template_id else None
    if not isinstance(template_record, dict):
        template_id = new_id()
        template_record = {
            "id": template_id,
            "category_id": cid,
            "name": f"Мастер-шаблон: {str(category_name or cid).strip()}",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        templates[template_id] = template_record
        cat_to_tpls.setdefault(cid, [])
        if template_id not in cat_to_tpls[cid]:
            cat_to_tpls[cid].insert(0, template_id)
    else:
        template_record["updated_at"] = _now_iso()
        templates[template_id] = template_record

    if not isinstance(template_record, dict):
        template_record = {
            "id": template_id or new_id(),
            "category_id": cid,
            "name": f"Мастер-шаблон: {str(category_name or cid).strip()}",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        template_id = str(template_record["id"])
        templates[template_id] = template_record
        cat_to_tpls.setdefault(cid, [])
        if template_id not in cat_to_tpls[cid]:
            cat_to_tpls[cid].insert(0, template_id)

    existing_attrs = attrs_by_tpl.get(template_id) if isinstance(attrs_by_tpl.get(template_id), list) else []
    existing_by_code: Dict[str, Dict[str, Any]] = {}
    for item in existing_attrs or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip().lower()
        if code and code not in existing_by_code:
            existing_by_code[code] = item

    attrs: List[Dict[str, Any]] = []
    next_position = 0

    for base_def in base_template_fields():
        existing_attr = existing_by_code.get(str(base_def.get("code") or "").strip().lower())
        row = next(
            (
                r for r in norm_rows
                if base_field_by_name(r.get("catalog_name")) and str(base_field_by_name(r.get("catalog_name")).get("key") or "") == str(base_def.get("key") or "")
            ),
            None,
        )
        if not row:
            row = {
                "catalog_name": str(base_def.get("name") or ""),
                "group": str(base_def.get("param_group") or ""),
                "provider_map": {
                    provider: {"id": "", "name": "", "kind": "", "values": [], "required": False, "export": False}
                    for provider in MAPPING_PROVIDERS
                },
                "confirmed": False,
            }
        a = _row_to_template_attr(row, next_position, existing=existing_attr)
        if a:
            attrs.append(a)
            next_position += 1

    for r in norm_rows:
        if is_base_field_name(r.get("catalog_name")):
            continue
        code = slugify_code(str(r.get("catalog_name") or ""))
        a = _row_to_template_attr(r, next_position, existing=existing_by_code.get(code))
        if a:
            attrs.append(a)
            next_position += 1

    split = split_template_attrs(attrs)
    template_meta = template_record.get("meta") if isinstance(template_record.get("meta"), dict) else {}
    sources_meta: Dict[str, Any] = {}
    if effective_yandex_category_id or yandex_params:
        sources_meta["yandex_market"] = {
            "enabled": True,
            "mode": "structure_source",
            "category_id": effective_yandex_category_id or None,
            "category_name": effective_yandex_category_name or None,
            "params_count": len(yandex_params),
            "required_params_count": yandex_required_count,
            "mapped_rows": sum(
                1
                for r in norm_rows
                if str((((r.get("provider_map") or {}).get("yandex_market") or {}).get("id") or "").strip())
            ),
        }
    effective_ozon_category_id = _effective_provider_category_id(category_id, "ozon", mappings, parent_by_id)
    ozon_params = _load_ozon_params(effective_ozon_category_id)
    ozon_required_count = len([x for x in ozon_params if bool(x.get("required") or False)])
    effective_ozon_category_name = _provider_category_name("ozon", effective_ozon_category_id)
    if effective_ozon_category_id or ozon_params:
        sources_meta["ozon"] = {
            "enabled": True,
            "mode": "structure_source",
            "category_id": effective_ozon_category_id or None,
            "category_name": effective_ozon_category_name or None,
            "params_count": len(ozon_params),
            "required_params_count": ozon_required_count,
            "mapped_rows": sum(
                1
                for r in norm_rows
                if str((((r.get("provider_map") or {}).get("ozon") or {}).get("id") or "").strip())
            ),
        }
    template_meta["sources"] = sources_meta
    template_meta["master_template"] = {
        "version": 2,
        "base_count": len(split["base"]),
        "category_count": len(split["category"]),
        "base_keys": [str((base_field_by_code(a.get("code")) or {}).get("key") or "") for a in split["base"]],
        "row_count": len(norm_rows),
        "confirmed_count": sum(1 for r in norm_rows if bool(r.get("confirmed") or False)),
    }
    template_record["meta"] = template_meta

    attrs_by_tpl[template_id] = attrs
    db["templates"] = templates
    db["attributes"] = attrs_by_tpl
    db["category_to_templates"] = cat_to_tpls
    db.setdefault("category_to_template", {})
    if isinstance(db.get("category_to_template"), dict):
        db["category_to_template"][cid] = template_id
    save_template_category_doc(
        cid,
        template_record,
        attrs,
        cat_to_tpls.get(cid) if isinstance(cat_to_tpls.get(cid), list) else [template_id],
    )


def _backfill_templates_from_attr_mapping() -> None:
    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not isinstance(items, dict) or not items:
        return
    nodes = _load_catalog_nodes()
    catalog_by_id = {str(x.get("id") or ""): x for x in _catalog_rows(nodes)}
    mappings = _load_mappings()
    parent_by_id = _catalog_parent_map(nodes)
    for cid, payload in items.items():
        sid = str(cid or "").strip()
        if not sid or not isinstance(payload, dict):
            continue
        rows = _normalize_attr_rows(payload.get("rows"))
        if not rows:
            continue
        cname = str((catalog_by_id.get(sid) or {}).get("name") or sid)
        _upsert_template_from_attr_mapping(
            sid,
            rows,
            cname,
            mappings=mappings,
            parent_by_id=parent_by_id,
        )
        _upsert_attr_values_dictionary_for_category(
            sid,
            rows,
            mappings=mappings,
            parent_by_id=parent_by_id,
        )


def _yandex_param_values(provider_category_id: str, attribute_id: str) -> List[str]:
    if not provider_category_id or not attribute_id:
        return []
    doc = read_doc(YANDEX_CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return []
    row = items.get(str(provider_category_id))
    if not isinstance(row, dict):
        return []
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    result = raw.get("result") if isinstance(raw, dict) else {}
    params = result.get("parameters") if isinstance(result, dict) else []
    if not isinstance(params, list):
        return []
    aid = str(attribute_id).strip()
    for p in params:
        if not isinstance(p, dict):
            continue
        pid = str(p.get("id") or "").strip()
        if pid != aid:
            continue
        for key in ("values", "options", "enumValues", "suggestedValues"):
            vals = _extract_text_list(p.get(key))
            if vals:
                return vals[:200]
    return []


def _catalog_attr_options_payload() -> List[Dict[str, Any]]:
    db = load_dictionaries_db()
    items = [x for x in (db.get("items") or []) if isinstance(x, dict)]
    items.sort(key=lambda x: str(x.get("title") or "").lower())
    return [
        {
            "id": it.get("attr_id") or it.get("id"),
            "title": it.get("title"),
            "code": it.get("code"),
            "type": it.get("type"),
            "scope": it.get("scope"),
            "dict_id": it.get("id"),
            "param_group": ((it.get("meta") or {}).get("param_group") if isinstance(it.get("meta"), dict) else None),
        }
        for it in items
    ]


def _catalog_attr_options_for_category(category_id: str) -> List[Dict[str, Any]]:
    cid = str(category_id or "").strip()
    if not cid:
        return []
    try:
        from app.api.routes import templates as templates_routes

        bootstrap = templates_routes.template_editor_bootstrap(cid)
    except Exception:
        return []

    master = bootstrap.get("master") if isinstance(bootstrap, dict) else {}
    category_attrs = master.get("category_attributes") if isinstance(master, dict) else []
    if not isinstance(category_attrs, list):
        return []

    out: List[Dict[str, Any]] = []
    used: set[str] = set()
    for attr in category_attrs:
        if not isinstance(attr, dict):
            continue
        title = str(attr.get("name") or "").strip()
        code = str(attr.get("code") or "").strip()
        options = attr.get("options") if isinstance(attr.get("options"), dict) else {}
        attr_id = str(attr.get("attribute_id") or options.get("attribute_id") or attr.get("id") or "").strip()
        dict_id = str(options.get("dict_id") or "").strip()
        key = _norm_name(title or code or attr_id)
        if not key or key in used:
            continue
        used.add(key)
        out.append(
            {
                "id": attr_id or code or title,
                "title": title or code or attr_id,
                "code": code or None,
                "type": attr.get("type"),
                "scope": attr.get("scope"),
                "dict_id": dict_id or None,
                "param_group": str(options.get("param_group") or "").strip() or None,
            }
        )
    return out


def _service_param_defs_payload() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    used_keys: set[str] = set()
    used_titles: set[str] = set()

    for field in base_template_fields():
        code = str(field.get("code") or "").strip().lower()
        name = str(field.get("name") or "").strip()
        if not code or not name:
            continue
        if code in used_keys or name.lower() in used_titles:
            continue
        out.append({"key": code, "title": name})
        used_keys.add(code)
        used_titles.add(name.lower())

    db = load_dictionaries_db()
    for d in db.get("items", []):
        if not isinstance(d, dict):
            continue
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        if not meta.get("service"):
            continue
        title = str(d.get("title") or "").strip()
        code = str(d.get("code") or "").strip()
        did = str(d.get("id") or "").strip()
        key = (code or did.replace("dict_", "")).replace(" ", "_").lower()
        if not key:
            continue
        if key in used_keys or title.lower() in used_titles:
            continue
        out.append({"key": key, "title": title})
        used_keys.add(key)
        used_titles.add(title.lower())
    return out


@router.get("/import/categories")
def mapping_import_categories() -> Dict[str, Any]:
    now = time.monotonic()
    cache_entry = _cache_entry(_import_categories_cache)
    cached = cache_entry.get("payload")
    cached_ts = float(cache_entry.get("ts") or 0.0)
    if cached and now - cached_ts < _IMPORT_CATEGORIES_CACHE_TTL_SECONDS:
        return cached
    persisted = _persistent_cache_read(_import_categories_cache_path(), _IMPORT_CATEGORIES_CACHE_TTL_SECONDS)
    if persisted:
        cache_entry["ts"] = now
        cache_entry["payload"] = persisted
        return persisted

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    mappings = _load_mappings()

    providers: List[Dict[str, Any]] = []
    provider_categories: Dict[str, List[Dict[str, Any]]] = {}

    for provider in sorted(PROVIDER_TITLES.keys()):
        items = _load_provider_categories(provider)
        has_mapping = any(str((row or {}).get(provider) or "").strip() for row in mappings.values() if isinstance(row, dict))
        if not items and not has_mapping:
            continue
        provider_categories[provider] = items
        providers.append(
            {
                "code": provider,
                "title": PROVIDER_TITLES.get(provider, provider),
                "count": len(items),
            }
        )

    binding_states = _build_binding_states(catalog_nodes, catalog_items, mappings)
    competitor_states = _build_competitor_states(catalog_nodes, catalog_items)

    payload = {
        "ok": True,
        "catalog_nodes": catalog_nodes,
        "catalog_items": catalog_items,
        "providers": providers,
        "provider_categories": provider_categories,
        "mappings": mappings,
        "binding_states": binding_states,
        "competitor_states": competitor_states,
    }
    cache_entry["ts"] = now
    cache_entry["payload"] = payload
    _persistent_cache_write(_import_categories_cache_path(), payload)
    return payload


@router.get("/import/categories/bootstrap")
def mapping_import_categories_bootstrap() -> Dict[str, Any]:
    payload = dict(mapping_import_categories())
    full_provider_categories = payload.get("provider_categories") if isinstance(payload.get("provider_categories"), dict) else {}
    mappings = payload.get("mappings") if isinstance(payload.get("mappings"), dict) else {}
    binding_states = payload.get("binding_states") if isinstance(payload.get("binding_states"), dict) else {}
    needed_by_provider: Dict[str, set[str]] = {provider: set() for provider in MAPPING_PROVIDERS}

    for row in mappings.values():
        if not isinstance(row, dict):
            continue
        for provider in MAPPING_PROVIDERS:
            provider_category_id = str(row.get(provider) or "").strip()
            if provider_category_id:
                needed_by_provider.setdefault(provider, set()).add(provider_category_id)

    for provider_states in binding_states.values():
        if not isinstance(provider_states, dict):
            continue
        for provider in MAPPING_PROVIDERS:
            state = provider_states.get(provider) if isinstance(provider_states.get(provider), dict) else {}
            for key in ("direct_id", "inherited_id", "effective_id"):
                provider_category_id = str(state.get(key) or "").strip()
                if provider_category_id:
                    needed_by_provider.setdefault(provider, set()).add(provider_category_id)
            for binding in state.get("child_bindings") or []:
                if not isinstance(binding, dict):
                    continue
                provider_category_id = str(binding.get("provider_category_id") or "").strip()
                if provider_category_id:
                    needed_by_provider.setdefault(provider, set()).add(provider_category_id)

    light_provider_categories: Dict[str, List[Dict[str, Any]]] = {}
    for provider, needed_ids in needed_by_provider.items():
        source_items = full_provider_categories.get(provider) if isinstance(full_provider_categories.get(provider), list) else []
        light_provider_categories[provider] = [
            item for item in source_items if str(item.get("id") or "").strip() in needed_ids
        ]

    payload["provider_categories"] = light_provider_categories
    payload["provider_categories_lazy"] = True
    return payload


@router.get("/import/categories/provider/{provider}")
def mapping_provider_categories(provider: str) -> Dict[str, Any]:
    provider_code = str(provider or "").strip()
    if provider_code not in PROVIDER_TITLES:
        raise HTTPException(status_code=404, detail="PROVIDER_NOT_FOUND")
    items = _load_provider_categories(provider_code)
    return {
        "ok": True,
        "provider": provider_code,
        "title": PROVIDER_TITLES.get(provider_code, provider_code),
        "items": items,
        "count": len(items),
    }


@router.get("/issues")
def mapping_issues() -> Dict[str, Any]:
    return {"ok": True, **audit_category_mapping_issues(limit=100)}


@router.post("/import/categories/validate-provider-category")
async def mapping_validate_provider_category(req: ValidateProviderCategoryReq) -> Dict[str, Any]:
    provider = str(req.provider or "").strip()
    provider_category_id = str(req.provider_category_id or "").strip()
    if provider != "ozon":
        raise HTTPException(status_code=400, detail="PROVIDER_VALIDATION_UNSUPPORTED")
    if not provider_category_id:
        raise HTTPException(status_code=400, detail="PROVIDER_CATEGORY_REQUIRED")

    from app.api.routes import connectors_status, ozon_market  # Local import avoids route import cycle.

    stores = connectors_status._enabled_ozon_stores(current_tenant_organization_id())  # noqa: SLF001
    if not stores:
        raise HTTPException(status_code=400, detail="OZON_IMPORT_STORES_MISSING")

    successes: List[Dict[str, Any]] = []
    errors: List[str] = []
    for store in stores:
        try:
            result = await ozon_market.import_category_attributes(
                ozon_market.ImportCategoryAttrsReq(
                    category_id=provider_category_id,
                    language="DEFAULT",
                    import_values=False,
                    token=str(store.get("api_key") or ""),
                    client_id=str(store.get("client_id") or ""),
                )
            )
            ozon_market.mark_category_attributes_validated(
                provider_category_id,
                store_id=str(store.get("id") or ""),
                store_title=str(store.get("title") or ""),
                client_id=str(store.get("client_id") or ""),
                type_ids=result.get("type_ids_used") if isinstance(result.get("type_ids_used"), list) else [],
            )
            successes.append(
                {
                    "store_id": str(store.get("id") or ""),
                    "store_title": str(store.get("title") or ""),
                    "client_id": str(store.get("client_id") or ""),
                    "attributes_count": int(result.get("attributes_count") or 0),
                    "type_ids_used": result.get("type_ids_used") if isinstance(result.get("type_ids_used"), list) else [],
                }
            )
        except Exception as e:
            errors.append(f"{store.get('title') or store.get('client_id')}: {e}")

    if not successes:
        tail = " | ".join(errors[-4:]) if errors else "NO_RESPONSE"
        raise HTTPException(status_code=404, detail=f"OZON_CATEGORY_NOT_VALIDATED {tail}")

    _invalidate_import_categories_cache()
    return {
        "ok": True,
        "provider": provider,
        "provider_category_id": provider_category_id,
        "validated_stores": successes,
        "errors": errors,
    }


@router.get("/import/attributes/bootstrap")
def mapping_attribute_bootstrap() -> Dict[str, Any]:
    now = time.monotonic()
    cache_entry = _cache_entry(_attr_bootstrap_cache)
    cached = cache_entry.get("payload")
    cached_ts = float(cache_entry.get("ts") or 0.0)
    if cached and now - cached_ts < _ATTR_BOOTSTRAP_CACHE_TTL_SECONDS:
        return cached
    persisted = _persistent_cache_read(_attr_bootstrap_cache_path(), _ATTR_BOOTSTRAP_CACHE_TTL_SECONDS)
    if persisted:
        cache_entry["ts"] = now
        cache_entry["payload"] = persisted
        return persisted

    categories_payload = mapping_attribute_categories()
    payload = {
        "ok": True,
        "items": categories_payload.get("items") if isinstance(categories_payload.get("items"), list) else [],
        "count": int(categories_payload.get("count") or 0),
        "catalog_attr_options": [],
        "service_param_defs": _service_param_defs_payload(),
    }
    cache_entry["ts"] = now
    cache_entry["payload"] = payload
    _persistent_cache_write(_attr_bootstrap_cache_path(), payload)
    return payload


class LinkCategoryReq(BaseModel):
    catalog_category_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_category_id: Optional[str] = None
    force_clear_descendants: bool = False


class ValidateProviderCategoryReq(BaseModel):
    provider: str = Field(min_length=1)
    provider_category_id: str = Field(min_length=1)


class ClearDescendantBindingsReq(BaseModel):
    catalog_category_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    preserve_templates: bool = True


def _preserve_templates_for_categories(
    category_ids: List[str],
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
    catalog_name_by_id: Dict[str, str],
) -> List[str]:
    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not isinstance(items, dict):
        return []
    preserved: List[str] = []
    for category_id in category_ids:
        cid = str(category_id or "").strip()
        payload = items.get(cid)
        if not cid or not isinstance(payload, dict):
            continue
        rows = _normalize_attr_rows(payload.get("rows"))
        if not rows:
            continue
        _upsert_template_from_attr_mapping(
            cid,
            rows,
            catalog_name_by_id.get(cid, cid),
            mappings=mappings,
            parent_by_id=parent_by_id,
        )
        _upsert_attr_values_dictionary_for_category(
            cid,
            rows,
            mappings=mappings,
            parent_by_id=parent_by_id,
        )
        preserved.append(cid)
    return sorted(set(preserved))


class AttrRowProviderBinding(BaseModel):
    id: str = ""
    name: str = ""
    kind: str = ""
    values: List[str] = Field(default_factory=list)
    required: bool = False
    export: bool = False
    match_source: str = ""
    match_confidence: Optional[float] = None
    match_reason: str = ""


class AttrRowProviderMap(AttrRowProviderBinding):
    bindings: List[AttrRowProviderBinding] = Field(default_factory=list)


class AttrRow(BaseModel):
    id: Optional[str] = None
    catalog_name: str = ""
    group: str = "О товаре"
    provider_map: Dict[str, AttrRowProviderMap] = Field(default_factory=dict)
    confirmed: bool = False


class SaveAttrMappingReq(BaseModel):
    rows: List[AttrRow] = Field(default_factory=list)
    apply_to_category_ids: List[str] = Field(default_factory=list)


class AiMatchReq(BaseModel):
    apply: bool = True


class ValueAiSuggestReq(BaseModel):
    provider: str
    apply: bool = True


class ValueExportMapPatchReq(BaseModel):
    provider: str
    canonical_value: str
    output_value: Optional[str] = None


_ATTR_AI_WORKFLOW = "marketplace_attribute_ai_match"
_ATTR_AI_JOB_TTL_SECONDS = 300.0
_VALUE_AI_WORKFLOW = "marketplace_value_ai_match"
_VALUE_AI_JOB_TTL_SECONDS = 300.0


def _job_ts(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _save_attr_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    upsert_pim_workflow_run(job, workflow=_ATTR_AI_WORKFLOW)
    return job


def _claim_attr_ai_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_pim_workflow_run_as_running(
        job_id,
        workflow=_ATTR_AI_WORKFLOW,
        payload_updates={
            "phase": "matching",
            "message": "Автоподбор проверяет спорные связки. Уверенные правила и подтвержденные связи применяются автоматически.",
            "started_at": _now_iso(),
            "updated_ts": time.time(),
        },
    )


def _save_value_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    upsert_pim_workflow_run(job, workflow=_VALUE_AI_WORKFLOW)
    return job


def _claim_value_ai_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_pim_workflow_run_as_running(
        job_id,
        workflow=_VALUE_AI_WORKFLOW,
        payload_updates={
            "phase": "matching",
            "message": "Автоподбор сопоставляет значения PIM со справочником площадки.",
            "started_at": _now_iso(),
            "updated_ts": time.time(),
        },
    )


def _prune_attr_ai_jobs() -> None:
    now = time.time()
    stale_after = max(_ATTR_AI_JOB_TTL_SECONDS, _ai_match_timeout_seconds() * 2.5)
    for job in list_pim_workflow_runs(workflow=_ATTR_AI_WORKFLOW, statuses=["queued", "running"], limit=200):
        updated = _job_ts(job.get("updated_ts") or job.get("created_ts"))
        if updated and now - updated > stale_after:
            job.update({
                "status": "failed",
                "phase": "stale",
                "message": "Автоподбор был прерван. Запустите подбор заново.",
                "finished_at": _now_iso(),
                "updated_ts": now,
                "error": "STALE_AI_MATCH_JOB",
            })
            _save_attr_ai_job(job)


def _prune_value_ai_jobs() -> None:
    now = time.time()
    stale_after = max(_VALUE_AI_JOB_TTL_SECONDS, _ai_match_timeout_seconds() * 2.5)
    for job in list_pim_workflow_runs(workflow=_VALUE_AI_WORKFLOW, statuses=["queued", "running"], limit=200):
        updated = _job_ts(job.get("updated_ts") or job.get("created_ts"))
        if updated and now - updated > stale_after:
            job.update({
                "status": "failed",
                "phase": "stale",
                "message": "Автоподбор значений был прерван. Запустите подбор заново.",
                "finished_at": _now_iso(),
                "updated_ts": now,
                "error": "STALE_VALUE_AI_MATCH_JOB",
            })
            _save_value_ai_job(job)


def _public_attr_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "job_id": str(job.get("job_id") or ""),
        "catalog_category_id": str(job.get("catalog_category_id") or ""),
        "status": str(job.get("status") or "queued"),
        "phase": str(job.get("phase") or ""),
        "message": str(job.get("message") or ""),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "engine": job.get("engine"),
        "ai_error": job.get("ai_error") or "",
        "rows_count": job.get("rows_count"),
        "summary": job.get("summary"),
        "error": job.get("error") or "",
    }
    return payload


def _public_value_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "job_id": str(job.get("job_id") or ""),
        "catalog_category_id": str(job.get("catalog_category_id") or ""),
        "dict_id": str(job.get("dict_id") or ""),
        "provider": str(job.get("provider") or ""),
        "status": str(job.get("status") or "queued"),
        "phase": str(job.get("phase") or ""),
        "message": str(job.get("message") or ""),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "engine": job.get("engine"),
        "ai_error": job.get("ai_error") or "",
        "summary": job.get("summary"),
        "error": job.get("error") or "",
    }


async def _run_attr_ai_match_job(job_id: str, catalog_category_id: str, req: AiMatchReq) -> None:
    job = get_pim_workflow_run(job_id, workflow=_ATTR_AI_WORKFLOW)
    if not job:
        return
    job.update({
        "status": "running",
        "phase": "matching",
        "message": "Автоподбор проверяет спорные связки. Уверенные правила и подтвержденные связи применяются автоматически.",
        "started_at": _now_iso(),
        "updated_ts": time.time(),
    })
    _save_attr_ai_job(job)
    try:
        result = await mapping_attribute_ai_match(catalog_category_id, req)
        job.update({
            "status": "completed",
            "phase": "completed",
            "message": "Автоподбор завершен. Обновите список параметров и проверьте спорные строки.",
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "engine": result.get("engine"),
            "ai_error": result.get("ai_error") or "",
            "rows_count": result.get("rows_count"),
            "summary": result.get("summary"),
        })
        _save_attr_ai_job(job)
    except Exception as exc:
        job.update({
            "status": "failed",
            "phase": "failed",
            "message": "Автоподбор не завершился. Правила и подтвержденные связи можно применить повторно.",
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "error": f"{exc.__class__.__name__}: {str(exc).strip()}"[:500],
        })
        _save_attr_ai_job(job)


async def _run_value_ai_match_job(job_id: str, catalog_category_id: str, dict_id: str, req: ValueAiSuggestReq) -> None:
    job = get_pim_workflow_run(job_id, workflow=_VALUE_AI_WORKFLOW)
    if not job:
        return
    job.update({
        "status": "running",
        "phase": "matching",
        "message": "Автоподбор сопоставляет значения PIM со справочником площадки.",
        "started_at": _now_iso(),
        "updated_ts": time.time(),
    })
    _save_value_ai_job(job)
    try:
        result = await mapping_value_ai_suggest(catalog_category_id, dict_id, req)
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        suggestions_count = int(summary.get("suggestions") or 0) if isinstance(summary, dict) else 0
        job.update({
            "status": "completed",
            "phase": "completed",
            "message": (
                f"Автоподбор значений завершен: {suggestions_count} знач."
                if suggestions_count
                else str(result.get("message") or "Автоподбор значений завершен.")
            ),
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "engine": summary.get("engine") if isinstance(summary, dict) else None,
            "ai_error": result.get("ai_error") or "",
            "summary": summary,
        })
        _save_value_ai_job(job)
    except Exception as exc:
        job.update({
            "status": "failed",
            "phase": "failed",
            "message": "Автоподбор значений не завершился. Запустите подбор заново.",
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "error": f"{exc.__class__.__name__}: {str(exc).strip()}"[:500],
        })
        _save_value_ai_job(job)


def _json_extract(text: str) -> Optional[Dict[str, Any]]:
    s = str(text or "").strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return None
    raw = m.group(0)
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _norm_name(s: str) -> str:
    t = str(s or "").lower().strip()
    t = re.sub(r"\(.*?\)", " ", t)
    t = t.replace("ё", "е")
    t = re.sub(r"[,:;./\\|+_#№\"'`~!?-]+", " ", t)
    t = re.sub(r"\b(мм|см|гц|ом|вт|г|ч|мин|mah|мaч|ip)\b", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokens(s: str) -> set[str]:
    t = _norm_name(s)
    if not t:
        return set()
    out = {x for x in t.split(" ") if x}
    syn = {
        "цвет": {"окрас", "расцветка"},
        "шумоподавление": {"anc"},
        "беспроводные": {"беспроводной"},
        "интерфейсы": {"связи"},
        "версия": {"модуль"},
        "импеданс": {"сопротивление"},
        "наушников": {"наушники"},
    }
    ext = set(out)
    for w in list(out):
        for key, vals in syn.items():
            if w == key or w in vals:
                ext.add(key)
                ext.update(vals)
    return ext


def _kind_group(kind: str) -> str:
    k = str(kind or "").lower()
    if any(x in k for x in ("bool", "boolean", "да/нет")):
        return "bool"
    if any(x in k for x in ("enum", "select", "string")):
        return "text"
    if any(x in k for x in ("numeric", "decimal", "integer", "number", "float")):
        return "number"
    if any(x in k for x in ("text", "json", "url")):
        return "text"
    return "text"


def _feedback_bonus(
    y: Dict[str, Any],
    o: Dict[str, Any],
    feedback_doc: Optional[Dict[str, Any]],
) -> float:
    if not isinstance(feedback_doc, dict):
        return 0.0
    pair_feedback = feedback_doc.get("pair_feedback") if isinstance(feedback_doc.get("pair_feedback"), dict) else {}
    name_feedback = feedback_doc.get("name_feedback") if isinstance(feedback_doc.get("name_feedback"), dict) else {}

    yid = str(y.get("id") or "").strip()
    oid = str(o.get("id") or "").strip()
    pair_key = f"{yid}|{oid}" if yid and oid else ""

    y_name = _norm_name(str(y.get("name") or ""))
    o_name = _norm_name(str(o.get("name") or ""))
    name_key = f"{y_name}|{o_name}" if y_name and o_name else ""

    def score_row(row: Dict[str, Any]) -> float:
        ok = int(row.get("ok") or 0)
        bad = int(row.get("bad") or 0)
        total = ok + bad
        if total <= 0:
            return 0.0
        ratio = (ok - bad) / total
        return max(-1.0, min(1.0, ratio))

    bonus = 0.0
    if pair_key and pair_key in pair_feedback and isinstance(pair_feedback[pair_key], dict):
        bonus += 0.45 * score_row(pair_feedback[pair_key])
    if name_key and name_key in name_feedback and isinstance(name_feedback[name_key], dict):
        bonus += 0.25 * score_row(name_feedback[name_key])
    return bonus


def _pair_score(
    y: Dict[str, Any],
    o: Dict[str, Any],
    feedback_doc: Optional[Dict[str, Any]] = None,
) -> float:
    y_name = _norm_name(str(y.get("name") or ""))
    o_name = _norm_name(str(o.get("name") or ""))
    y_is_ram = bool(re.search(r"\b(оперативная|ram|озу)\b", y_name))
    o_is_ram = bool(re.search(r"\b(оперативная|ram|озу)\b", o_name))
    y_is_storage = bool(re.search(r"\b(встроенная|внутренняя|storage|rom|накопител)\b", y_name))
    o_is_storage = bool(re.search(r"\b(встроенная|внутренняя|storage|rom|накопител)\b", o_name))
    if (y_is_ram and o_is_storage) or (y_is_storage and o_is_ram):
        return 0.0
    yt = _tokens(str(y.get("name") or ""))
    ot = _tokens(str(o.get("name") or ""))
    if not yt or not ot:
        return 0.0
    inter = len(yt & ot)
    union = max(1, len(yt | ot))
    j = inter / union
    sub = 0.2 if (y_name and o_name and (y_name in o_name or o_name in y_name)) else 0.0
    kind_bonus = 0.1 if _kind_group(str(y.get("kind") or "")) == _kind_group(str(o.get("kind") or "")) else 0.0
    feedback = _feedback_bonus(y, o, feedback_doc)
    return j + sub + kind_bonus + feedback


def _service_names() -> List[str]:
    doc = load_dictionaries_db()
    out = list(DEFAULT_SERVICE_NAMES)
    used = {x.strip().lower() for x in out}
    for it in doc.get("items") or []:
        if not isinstance(it, dict):
            continue
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        if not bool(meta.get("service")):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        key = title.lower()
        if key in used:
            continue
        out.append(title)
        used.add(key)
    return out


def _empty_provider_binding() -> Dict[str, Any]:
    return _provider_map_payload({})


def _build_row(
    catalog_name: str,
    y: Optional[Dict[str, Any]],
    confirmed: bool = False,
    group: Optional[str] = None,
    oz: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    y_name = str((y or {}).get("name") or "").strip()
    oz_name = str((oz or {}).get("name") or "").strip()
    return {
        "id": str(uuid4()),
        "catalog_name": str(catalog_name or "").strip(),
        "group": _normalize_param_group(group, str(catalog_name or ""), y_name or oz_name),
        "provider_map": {
            "yandex_market": {
                "id": str((y or {}).get("id") or "").strip(),
                "name": y_name,
                "kind": str((y or {}).get("kind") or "").strip(),
                "values": _extract_text_list((y or {}).get("values")),
                "required": bool((y or {}).get("required") or False),
                "export": bool(y),
                "bindings": _provider_binding_list(y or {}),
            },
            "ozon": {
                "id": str((oz or {}).get("id") or "").strip(),
                "name": oz_name,
                "kind": str((oz or {}).get("kind") or "").strip(),
                "values": _extract_text_list((oz or {}).get("values")),
                "required": bool((oz or {}).get("required") or False),
                "export": bool(oz),
                "bindings": _provider_binding_list(oz or {}),
            },
        },
        "confirmed": bool(confirmed),
    }


def _record_feedback_from_rows(
    old_rows: List[Dict[str, Any]],
    new_rows: List[Dict[str, Any]],
) -> None:
    _ = old_rows
    _ = new_rows
    return


def _deterministic_ai_rows(
    yandex_params: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
    feedback_doc: Optional[Dict[str, Any]] = None,
    ozon_params: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    out = [dict(r) for r in _normalize_attr_rows(existing_rows)]
    yz = [x for x in yandex_params if isinstance(x, dict)]
    used_yids: set[str] = {
        str((((row.get("provider_map") or {}).get("yandex_market") or {}).get("id") or "")).strip()
        for row in out
        if isinstance(row, dict)
    }

    for y in yz:
        yid = str(y.get("id") or "").strip()
        if not yid or yid in used_yids:
            continue

        best_idx = -1
        best_score = 0.0
        for idx, row in enumerate(out):
            row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            y_map = row_map.get("yandex_market") if isinstance(row_map.get("yandex_market"), dict) else {}
            if str(y_map.get("id") or "").strip():
                continue
            row_name = str(row.get("catalog_name") or "").strip()
            if not row_name:
                continue
            score = _pair_score(
                {"id": "", "name": row_name, "kind": str(row.get("group") or "")},
                y,
                feedback_doc=feedback_doc,
            )
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx < 0 or best_score < 0.34:
            continue

        row = dict(out[best_idx])
        provider_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        provider_map["yandex_market"] = {
            "id": yid,
            "name": str(y.get("name") or yid),
            "kind": str(y.get("kind") or "").strip(),
            "values": _extract_text_list(y.get("values"))[:120],
            "required": bool(y.get("required") or False),
            "export": True,
            "match_source": "rule",
            "match_confidence": round(best_score, 3),
            "match_reason": "Автоподбор по похожести названия PIM-поля и параметра Я.Маркета.",
            "bindings": _provider_binding_list(
                {
                    **y,
                    "id": yid,
                    "export": True,
                    "match_source": "rule",
                    "match_confidence": round(best_score, 3),
                    "match_reason": "Автоподбор по похожести названия PIM-поля и параметра Я.Маркета.",
                }
            ),
        }
        row["provider_map"] = provider_map
        row["confirmed"] = bool(row.get("confirmed") or best_score >= 0.75)
        out[best_idx] = row
        used_yids.add(yid)

    oz = [x for x in (ozon_params or []) if isinstance(x, dict)]
    used_oids: set[str] = {
        str((((row.get("provider_map") or {}).get("ozon") or {}).get("id") or "")).strip()
        for row in out
        if isinstance(row, dict)
    }

    for o in oz:
        oid = str(o.get("id") or "").strip()
        if not oid or oid in used_oids:
            continue

        best_idx = -1
        best_score = 0.0
        for idx, row in enumerate(out):
            row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            oz_map = row_map.get("ozon") if isinstance(row_map.get("ozon"), dict) else {}
            if str(oz_map.get("id") or "").strip():
                continue
            row_name = str(row.get("catalog_name") or "").strip()
            if not row_name:
                continue
            score = _pair_score(
                {"id": "", "name": row_name, "kind": str(row.get("group") or "")},
                o,
                feedback_doc=feedback_doc,
            )
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx < 0 or best_score < 0.34:
            continue

        row = dict(out[best_idx])
        provider_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        provider_map["ozon"] = {
            "id": oid,
            "name": str(o.get("name") or oid),
            "kind": str(o.get("kind") or "").strip(),
            "values": _extract_text_list(o.get("values"))[:120],
            "required": bool(o.get("required") or False),
            "export": True,
            "match_source": "rule",
            "match_confidence": round(best_score, 3),
            "match_reason": "Автоподбор по похожести названия PIM-поля и параметра Ozon.",
            "bindings": _provider_binding_list(
                {
                    **o,
                    "id": oid,
                    "export": True,
                    "match_source": "rule",
                    "match_confidence": round(best_score, 3),
                    "match_reason": "Автоподбор по похожести названия PIM-поля и параметра Ozon.",
                }
            ),
        }
        row["provider_map"] = provider_map
        row["confirmed"] = bool(row.get("confirmed") or best_score >= 0.75)
        out[best_idx] = row
        used_oids.add(oid)

    return _normalize_attr_rows(out)


def _prune_rows_for_current_provider_params(
    rows: List[Dict[str, Any]],
    yandex_params: List[Dict[str, Any]],
    ozon_params: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    valid_yandex_ids = {str(x.get("id") or "").strip() for x in yandex_params if str(x.get("id") or "").strip()}
    valid_ozon_ids = {str(x.get("id") or "").strip() for x in ozon_params if str(x.get("id") or "").strip()}
    pruned: List[Dict[str, Any]] = []

    def _prune_provider_binding(raw: Dict[str, Any], valid_ids: set[str]) -> Dict[str, Any]:
        bindings = [
            item
            for item in _provider_binding_list(raw)
            if not str(item.get("id") or "").strip() or str(item.get("id") or "").strip() in valid_ids
        ]
        if not bindings:
            return _empty_provider_binding()
        primary_id = str(raw.get("id") or "").strip()
        primary = next((item for item in bindings if str(item.get("id") or "").strip() == primary_id), bindings[0])
        payload = dict(primary)
        payload["bindings"] = bindings
        return _provider_map_payload(payload)

    for row in _normalize_attr_rows(rows):
        name = str(row.get("catalog_name") or "").strip()
        provider_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        y_map = dict(provider_map.get("yandex_market") or {}) if isinstance(provider_map.get("yandex_market"), dict) else _empty_provider_binding()
        oz_map = dict(provider_map.get("ozon") or {}) if isinstance(provider_map.get("ozon"), dict) else _empty_provider_binding()

        had_provider_binding = bool(_provider_binding_list(y_map) or _provider_binding_list(oz_map))
        y_map = _prune_provider_binding(y_map, valid_yandex_ids)
        oz_map = _prune_provider_binding(oz_map, valid_ozon_ids)

        has_valid_binding = bool(_provider_binding_list(y_map) or _provider_binding_list(oz_map))
        keep_without_binding = (
            bool(row.get("confirmed") or False)
            or is_base_field_name(name)
            or _is_service_catalog_name(name)
            or not had_provider_binding
        )
        if not has_valid_binding and not keep_without_binding:
            continue

        next_row = dict(row)
        next_row["provider_map"] = {
            "yandex_market": y_map,
            "ozon": oz_map,
        }
        pruned.append(next_row)

    return _normalize_attr_rows(pruned)


def _catalog_target_rows(
    catalog_attr_options: List[Dict[str, Any]],
    service_param_defs: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    used: set[str] = set()

    for item in service_param_defs or []:
        title = canonical_base_field_name(_humanize_catalog_name(item.get("title")))
        if not title:
            continue
        key = _norm_name(title)
        if not key or key in used:
            continue
        used.add(key)
        out.append(_build_row(title, None, confirmed=False, group=_normalize_param_group(None, title)))

    for item in catalog_attr_options or []:
        title = canonical_base_field_name(_humanize_catalog_name(item.get("title")))
        if not title:
            continue
        key = _norm_name(title)
        if not key or key in used:
            continue
        used.add(key)
        out.append(
            _build_row(
                title,
                None,
                confirmed=False,
                group=_normalize_param_group(item.get("param_group"), title),
            )
        )

    return _normalize_attr_rows(out)


def _provider_param_target_options(*provider_param_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    used: set[str] = set()
    for params in provider_param_lists:
        if not isinstance(params, list):
            continue
        for param in params:
            if not isinstance(param, dict):
                continue
            title = canonical_base_field_name(_humanize_catalog_name(param.get("name") or param.get("title")))
            if not title:
                continue
            key = _norm_name(title)
            if not key or key in used:
                continue
            used.add(key)
            out.append(
                {
                    "id": str(param.get("id") or title),
                    "title": title,
                    "type": _kind_to_template_type(str(param.get("kind") or "")),
                    "param_group": _normalize_param_group(None, title),
                }
            )
    return out


def _merge_existing_into_target_rows(
    target_rows: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = [dict(r) for r in _normalize_attr_rows(target_rows)]
    by_name: Dict[str, int] = {
        _norm_name(str(row.get("catalog_name") or "")): idx
        for idx, row in enumerate(merged)
        if _norm_name(str(row.get("catalog_name") or ""))
    }

    for row in _normalize_attr_rows(existing_rows):
        key = _norm_name(str(row.get("catalog_name") or ""))
        if key and key in by_name:
            cur = dict(merged[by_name[key]])
            cur_map = cur.get("provider_map") if isinstance(cur.get("provider_map"), dict) else {}
            row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            for provider in MAPPING_PROVIDERS:
                cur_payload = cur_map.get(provider) if isinstance(cur_map.get(provider), dict) else _empty_provider_binding()
                row_payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else _empty_provider_binding()
                if (
                    not str(cur_payload.get("id") or "").strip()
                    and (
                        str(row_payload.get("id") or "").strip()
                        or str(row_payload.get("name") or "").strip()
                    )
                ):
                    cur_map[provider] = row_payload
            cur["provider_map"] = cur_map
            cur["confirmed"] = bool(cur.get("confirmed") or row.get("confirmed"))
            if str(row.get("group") or "").strip():
                cur["group"] = _normalize_param_group(row.get("group"), cur.get("catalog_name"))
            merged[by_name[key]] = cur
            continue

        has_binding = any(
            str((((row.get("provider_map") or {}).get(provider) or {}).get("id") or "")).strip()
            for provider in MAPPING_PROVIDERS
        )
        if has_binding or bool(row.get("confirmed") or False):
            merged.append(row)

    return _normalize_attr_rows(merged)


def _merge_ai_rows_into_target_rows(
    target_rows: List[Dict[str, Any]],
    ai_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged = [dict(r) for r in _normalize_attr_rows(target_rows)]
    by_name: Dict[str, int] = {
        _norm_name(str(row.get("catalog_name") or "")): idx
        for idx, row in enumerate(merged)
        if _norm_name(str(row.get("catalog_name") or ""))
    }

    for row in _normalize_attr_rows(ai_rows):
        key = _norm_name(str(row.get("catalog_name") or ""))
        if not key or key not in by_name:
            continue
        cur = dict(merged[by_name[key]])
        cur_map = cur.get("provider_map") if isinstance(cur.get("provider_map"), dict) else {}
        row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        for provider in MAPPING_PROVIDERS:
            row_payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else _empty_provider_binding()
            if str(row_payload.get("id") or "").strip():
                row_payload = _annotate_provider_payload(
                    row_payload,
                    source="ai",
                    reason="Предложено AI по смыслу PIM-поля и параметра площадки.",
                )
                cur_map[provider] = row_payload
        cur["provider_map"] = cur_map
        cur["confirmed"] = bool(cur.get("confirmed") or row.get("confirmed"))
        merged[by_name[key]] = cur

    return _normalize_attr_rows(merged)


def _provider_payload_has_binding(payload: Dict[str, Any]) -> bool:
    return bool(_provider_binding_list(payload))


def _fill_missing_provider_metadata_from_memory(
    rows: List[Dict[str, Any]],
    before_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    before_keys: set[tuple[str, str, str]] = set()
    for row in _normalize_attr_rows(before_rows):
        row_key = _norm_name(str(row.get("catalog_name") or row.get("id") or ""))
        row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        for provider in MAPPING_PROVIDERS:
            payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else {}
            for item in _provider_binding_list(payload):
                binding_key = str(item.get("id") or item.get("name") or "").strip()
                if row_key and binding_key:
                    before_keys.add((row_key, provider, binding_key))

    out: List[Dict[str, Any]] = []
    for row in _normalize_attr_rows(rows):
        row_key = _norm_name(str(row.get("catalog_name") or row.get("id") or ""))
        next_row = dict(row)
        next_map = dict(next_row.get("provider_map") or {}) if isinstance(next_row.get("provider_map"), dict) else {}
        for provider in MAPPING_PROVIDERS:
            payload = next_map.get(provider) if isinstance(next_map.get(provider), dict) else {}
            if not _provider_payload_has_binding(payload):
                continue
            if str(payload.get("match_source") or "").strip():
                continue
            binding_keys = [
                str(item.get("id") or item.get("name") or "").strip()
                for item in _provider_binding_list(payload)
                if str(item.get("id") or item.get("name") or "").strip()
            ]
            source = "memory" if any((row_key, provider, key) in before_keys for key in binding_keys) else "rule"
            reason = (
                "Сохраненная ранее привязка категории; используется как память сопоставления."
                if source == "memory"
                else "Автосвязь без сохраненного источника; требуется проверка пользователем."
            )
            next_map[provider] = _annotate_provider_payload(payload, source=source, reason=reason)
        next_row["provider_map"] = next_map
        out.append(next_row)
    return _normalize_attr_rows(out)


def _annotate_provider_payload(payload: Dict[str, Any], *, source: str, reason: str) -> Dict[str, Any]:
    annotated = _provider_map_payload(payload)
    if not str(annotated.get("match_source") or "").strip():
        annotated["match_source"] = source
    if not str(annotated.get("match_reason") or "").strip():
        annotated["match_reason"] = reason
    bindings = []
    for item in _provider_binding_list(annotated):
        next_item = dict(item)
        if not str(next_item.get("match_source") or "").strip():
            next_item["match_source"] = str(annotated.get("match_source") or source)
        if not str(next_item.get("match_reason") or "").strip():
            next_item["match_reason"] = str(annotated.get("match_reason") or reason)
        if annotated.get("match_confidence") is not None and next_item.get("match_confidence") is None:
            next_item["match_confidence"] = annotated.get("match_confidence")
        bindings.append(next_item)
    annotated["bindings"] = bindings
    return annotated


def _attr_row_provider_coverage(row: Dict[str, Any], providers: Optional[List[str]] = None) -> int:
    provider_codes = providers or MAPPING_PROVIDERS
    row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    covered = 0
    for provider in provider_codes:
        payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else {}
        if str(payload.get("id") or payload.get("name") or "").strip():
            covered += 1
    return covered


def _attr_row_signature(row: Dict[str, Any], providers: Optional[List[str]] = None) -> Dict[str, Any]:
    provider_codes = providers or MAPPING_PROVIDERS
    row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    return {
        "confirmed": bool(row.get("confirmed") or False),
        "providers": {
            provider: str(
                (
                    row_map.get(provider)
                    if isinstance(row_map.get(provider), dict)
                    else {}
                ).get("id")
                or ""
            ).strip()
            for provider in provider_codes
        },
    }


def _is_service_attr_row(row: Dict[str, Any]) -> bool:
    rid = str(row.get("id") or "").strip()
    if rid.startswith("svc:"):
        return True
    name = _norm_name(str(row.get("catalog_name") or ""))
    if name in {"sku gt", "sku", "название"}:
        return True
    return (
        "sku" in name
        or "штрихкод" in name
        or "barcode" in name
        or "наименование" in name
        or "бренд" in name
        or "описание" in name
        or "фото" in name
        or "картин" in name
    )


def _is_core_export_attr_row(row: Dict[str, Any]) -> bool:
    name = _norm_name(str(row.get("catalog_name") or ""))
    rid = str(row.get("id") or "").strip().lower()
    protected_names = {
        "sku",
        "sku gt",
        "наименование",
        "наименование товара",
        "название",
        "название товара",
        "описание",
        "описание товара",
        "фото",
        "картинки",
        "изображения",
    }
    protected_ids = {"svc:sku_gt", "svc:title", "svc:description", "svc:media_images"}
    return name in protected_names or rid in protected_ids


def _clear_core_export_provider_bindings(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in _normalize_attr_rows(rows):
        if not _is_core_export_attr_row(row):
            out.append(row)
            continue
        next_row = dict(row)
        next_row["provider_map"] = {provider: _empty_provider_binding() for provider in MAPPING_PROVIDERS}
        next_row["confirmed"] = True
        out.append(next_row)
    return _normalize_attr_rows(out)


def _attr_mapping_snapshot(rows: List[Dict[str, Any]], providers: Optional[List[str]] = None) -> Dict[str, Any]:
    normalized = [row for row in _normalize_attr_rows(rows) if not _is_service_attr_row(row)]
    total = len(normalized)
    ready = 0
    unmapped = 0
    provider_counts = {provider: 0 for provider in (providers or MAPPING_PROVIDERS)}
    sample_unmapped: List[str] = []
    for row in normalized:
        coverage = _attr_row_provider_coverage(row, providers)
        if coverage == 0:
            unmapped += 1
            if len(sample_unmapped) < 8:
                sample_unmapped.append(str(row.get("catalog_name") or row.get("id") or "").strip())
        if coverage > 0 and bool(row.get("confirmed") or False):
            ready += 1
        row_map = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        for provider in provider_counts:
            payload = row_map.get(provider) if isinstance(row_map.get(provider), dict) else {}
            if str(payload.get("id") or payload.get("name") or "").strip():
                provider_counts[provider] += 1
    return {
        "total": total,
        "ready": ready,
        "attention": total - ready,
        "unmapped": unmapped,
        "providers": provider_counts,
        "sample_unmapped": [item for item in sample_unmapped if item],
    }


def _attr_ai_run_summary(before_rows: List[Dict[str, Any]], after_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    before = [row for row in _normalize_attr_rows(before_rows) if not _is_service_attr_row(row)]
    after = [row for row in _normalize_attr_rows(after_rows) if not _is_service_attr_row(row)]
    before_by_key = {
        str(row.get("id") or _norm_name(str(row.get("catalog_name") or ""))).strip(): row
        for row in before
    }
    changed_rows = 0
    improved_rows = 0
    provider_added = {provider: 0 for provider in MAPPING_PROVIDERS}

    for row in after:
        key = str(row.get("id") or _norm_name(str(row.get("catalog_name") or ""))).strip()
        prev = before_by_key.get(key) or {}
        prev_sig = _attr_row_signature(prev)
        next_sig = _attr_row_signature(row)
        if prev_sig != next_sig:
            changed_rows += 1
        prev_coverage = _attr_row_provider_coverage(prev)
        next_coverage = _attr_row_provider_coverage(row)
        if next_coverage > prev_coverage or (not bool(prev.get("confirmed") or False) and bool(row.get("confirmed") or False) and next_coverage > 0):
            improved_rows += 1
        for provider in MAPPING_PROVIDERS:
            if next_sig["providers"].get(provider) and not prev_sig["providers"].get(provider):
                provider_added[provider] += 1

    return {
        "changed_rows": changed_rows,
        "improved_rows": improved_rows,
        "provider_added": provider_added,
        "before": _attr_mapping_snapshot(before),
        "after": _attr_mapping_snapshot(after),
    }


async def _ollama_suggest_rows(
    category_name: str,
    yandex_params: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
    feedback_doc: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    base_url = str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    model = str(os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")).strip() or "qwen2.5:7b-instruct"
    normalized_existing = _normalize_attr_rows(existing_rows)
    yandex_candidates = [x for x in (yandex_params or []) if isinstance(x, dict)]
    ranked_ids: List[str] = []
    ranked_by_id: Dict[str, Dict[str, Any]] = {}
    for row in normalized_existing:
        row_name = str(row.get("catalog_name") or "").strip()
        if not row_name:
            continue
        scored = []
        for param in yandex_candidates:
            score = _pair_score(
                {"id": "", "name": row_name, "kind": str(row.get("group") or "")},
                param,
                feedback_doc=feedback_doc,
            )
            scored.append((score, str(param.get("id") or ""), param))
        scored.sort(key=lambda item: item[0], reverse=True)
        for score, param_id, param in scored[:8]:
            if score <= 0.0 or not param_id or param_id in ranked_by_id:
                continue
            ranked_ids.append(param_id)
            ranked_by_id[param_id] = param
    selected_yandex_params = [ranked_by_id[x] for x in ranked_ids[: min(32, len(ranked_ids))]]
    if not selected_yandex_params:
        selected_yandex_params = yandex_candidates[:16]

    market_text = "; ".join(
        f"{str(x.get('id') or '')}={str(x.get('name') or '')}"
        for x in selected_yandex_params[:24]
    )
    pim_text = "; ".join(str(r.get("catalog_name") or "") for r in normalized_existing)
    prompt = (
        "Верни только JSON без markdown: {\"rows\":[[\"pim_name\",\"yandex_id_or_null\"]]}. "
        "Сопоставь PIM-поля с параметрами Я.Маркета только при одинаковом смысле. "
        "Если не уверен, ставь null. Не сопоставляй SKU, штрихкод, название, описание, фото с характеристиками. "
        f"Категория: {str(category_name or '')[:120]}. "
        f"PIM: {pim_text}. "
        f"MARKET: {market_text}."
    )

    body = {
        "model": model,
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {
            "temperature": 0.0,
            "top_p": 0.8,
            "num_ctx": 4096,
            "num_predict": 400,
        },
        "prompt": prompt,
    }

    timeout_budget = _ai_match_timeout_seconds()
    timeout = httpx.Timeout(
        timeout_budget,
        connect=min(max(timeout_budget / 2.0, 0.1), 3.0),
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{base_url}/api/generate", json=body)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"OLLAMA_HTTP_{r.status_code}")
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}

    response_text = str(data.get("response") or "").strip() if isinstance(data, dict) else ""
    obj = _json_extract(response_text)
    if not obj:
        return None
    rows = obj.get("rows")
    if not isinstance(rows, list) and obj.get("pim_name"):
        rows = [obj]
    if not isinstance(rows, list):
        return None

    y_map = {str(x.get("id") or "").strip(): x for x in selected_yandex_params if str(x.get("id") or "").strip()}
    out: List[Dict[str, Any]] = []
    for rr in rows:
        if not isinstance(rr, dict):
            continue
        if isinstance(rr, list):
            rr = {
                "catalog_name": rr[0] if len(rr) > 0 else "",
                "group": "",
                "yandex_id": rr[1] if len(rr) > 1 else "",
                "confirmed": True,
            }
        name = str(rr.get("catalog_name") or "").strip()
        if not name:
            continue
        group = str(rr.get("group") or "").strip()
        yid = str(rr.get("yandex_id") or "").strip()
        y = y_map.get(yid) if yid else None
        out.append(_build_row(name, y, confirmed=bool(rr.get("confirmed") or False), group=group))
    return _normalize_attr_rows(out) if out else None


async def _ollama_suggest_rows_chunked(
    *,
    category_name: str,
    yandex_params: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
    feedback_doc: Optional[Dict[str, Any]] = None,
) -> Optional[List[Dict[str, Any]]]:
    rows = _normalize_attr_rows(existing_rows)
    if not rows:
        return None

    chunk_size = _ai_match_chunk_size()
    deadline = time.monotonic() + _ai_match_timeout_seconds()
    out: List[Dict[str, Any]] = []
    successes = 0

    for index in range(0, len(rows), chunk_size):
        if time.monotonic() >= deadline:
            break
        chunk = rows[index : index + chunk_size]
        remaining = max(deadline - time.monotonic(), 1.0)
        try:
            async with asyncio.timeout(remaining):
                suggested = await _ollama_suggest_rows(
                    category_name=category_name,
                    yandex_params=yandex_params,
                    existing_rows=chunk,
                    feedback_doc=feedback_doc,
                )
        except Exception:
            suggested = None
        if suggested:
            successes += 1
            out.extend(suggested)
        else:
            out.extend(chunk)

    if successes <= 0:
        return None
    if len(out) < len(rows):
        out.extend(rows[len(out) :])
    return _normalize_attr_rows(out) if out else None


@router.get("/import/attributes/value-options")
async def mapping_attribute_value_options(
    catalog_category_id: str,
    provider: str,
    attribute_id: str,
    refresh: bool = False,
) -> Dict[str, Any]:
    cid = str(catalog_category_id or "").strip()
    p = str(provider or "").strip()
    aid = str(attribute_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if p not in set(MAPPING_PROVIDERS):
        raise HTTPException(status_code=400, detail="PROVIDER_INVALID")
    if not aid:
        raise HTTPException(status_code=400, detail="ATTRIBUTE_ID_REQUIRED")

    mappings = _load_mappings()
    parent_by_id = _catalog_parent_map(_load_catalog_nodes())
    provider_category_id = _effective_provider_category_id(cid, p, mappings, parent_by_id)
    if not provider_category_id:
        raise HTTPException(status_code=400, detail="CATEGORY_NOT_MAPPED_FOR_PROVIDER")

    values = _yandex_param_values(provider_category_id, aid)
    return {"ok": True, "provider": p, "attribute_id": aid, "values": values, "count": len(values)}


def _tree_maps(nodes: List[Dict[str, Any]]) -> tuple[Dict[str, Optional[str]], Dict[str, List[str]]]:
    parent_by_id: Dict[str, Optional[str]] = {}
    children_by_parent: Dict[str, List[str]] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        if not nid:
            continue
        pid = str(n.get("parent_id") or "").strip() or None
        parent_by_id[nid] = pid
        children_by_parent.setdefault(pid or "", []).append(nid)
    return parent_by_id, children_by_parent


def _ancestor_ids(node_id: str, parent_by_id: Dict[str, Optional[str]]) -> List[str]:
    out: List[str] = []
    seen = set()
    cur = parent_by_id.get(node_id)
    while cur and cur not in seen:
        seen.add(cur)
        out.append(cur)
        cur = parent_by_id.get(cur)
    return out


def _descendant_ids(node_id: str, children_by_parent: Dict[str, List[str]]) -> List[str]:
    out: List[str] = []
    stack = list(children_by_parent.get(node_id, []))
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children_by_parent.get(cur, []))
    return out


def _nearest_direct_ancestor(
    node_id: str,
    provider: str,
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, Optional[str]],
) -> str:
    cur = parent_by_id.get(node_id)
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = mappings.get(cur)
        if isinstance(row, dict):
            value = str(row.get(provider) or "").strip()
            if value:
                return cur
        cur = parent_by_id.get(cur)
    return ""


def _descendant_direct_binding_groups(
    node_id: str,
    provider: str,
    mappings: Dict[str, Dict[str, str]],
    children_by_parent: Dict[str, List[str]],
    catalog_path_by_id: Dict[str, str],
) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    stack = list(children_by_parent.get(node_id, []))
    seen: set[str] = set()
    while stack:
        cur = str(stack.pop() or "").strip()
        if not cur or cur in seen:
            continue
        seen.add(cur)
        row = mappings.get(cur)
        value = str((row or {}).get(provider) or "").strip() if isinstance(row, dict) else ""
        if value:
            item = grouped.get(value)
            if not item:
                item = {
                    "provider_category_id": value,
                    "provider_category_name": _provider_category_name(provider, value) or value,
                    "catalog_ids": [],
                    "catalog_paths": [],
                }
                grouped[value] = item
            item["catalog_ids"].append(cur)
            item["catalog_paths"].append(catalog_path_by_id.get(cur, cur))
        stack.extend(children_by_parent.get(cur, []))
    return sorted(
        grouped.values(),
        key=lambda item: str(item.get("provider_category_name") or item.get("provider_category_id") or "").lower(),
    )


def _build_binding_states(
    catalog_nodes: List[Dict[str, Any]],
    catalog_items: List[Dict[str, Any]],
    mappings: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, Any]]:
    parent_by_id, children_by_parent = _tree_maps(catalog_nodes)
    catalog_path_by_id = {
        str(item.get("id") or "").strip(): str(item.get("path") or item.get("name") or "").strip()
        for item in catalog_items
        if str(item.get("id") or "").strip()
    }
    out: Dict[str, Dict[str, Any]] = {}
    for item in catalog_items:
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue
        per_provider: Dict[str, Any] = {}
        for provider in MAPPING_PROVIDERS:
            row = mappings.get(cid)
            direct_id = str((row or {}).get(provider) or "").strip() if isinstance(row, dict) else ""
            inherited_from = ""
            inherited_id = ""
            child_bindings: List[Dict[str, Any]] = []
            if not direct_id:
                inherited_from = _nearest_direct_ancestor(cid, provider, mappings, parent_by_id)
                if inherited_from:
                    inherited_row = mappings.get(inherited_from)
                    inherited_id = str((inherited_row or {}).get(provider) or "").strip() if isinstance(inherited_row, dict) else ""
                child_bindings = _descendant_direct_binding_groups(
                    cid, provider, mappings, children_by_parent, catalog_path_by_id
                )
            state = "none"
            if direct_id:
                state = "direct"
            elif child_bindings:
                state = "aggregated_from_children"
            elif inherited_from and inherited_id:
                state = "inherited_from_parent"
            per_provider[provider] = {
                "state": state,
                "direct_id": direct_id or None,
                "inherited_from": inherited_from or None,
                "inherited_id": inherited_id or None,
                "effective_id": direct_id or inherited_id or None,
                "child_bindings": child_bindings,
            }
        out[cid] = per_provider
    return out


def _competitor_is_configured_row(row: Dict[str, Any]) -> bool:
    links = row.get("links") if isinstance(row.get("links"), dict) else {}
    has_restore = bool(str((links or {}).get("restore") or "").strip())
    has_store = bool(str((links or {}).get("store77") or "").strip())
    maps = row.get("mapping_by_site") if isinstance(row.get("mapping_by_site"), dict) else {}
    m_restore = maps.get("restore") if isinstance(maps, dict) else {}
    m_store = maps.get("store77") if isinstance(maps, dict) else {}
    has_map_restore = isinstance(m_restore, dict) and len(m_restore) > 0
    has_map_store = isinstance(m_store, dict) and len(m_store) > 0
    return bool(has_restore and has_store and has_map_restore and has_map_store)


def _competitor_templates_by_category() -> Dict[str, List[str]]:
    db = load_templates_db()
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    out: Dict[str, List[str]] = {}
    if isinstance(templates, dict):
        for tid, tpl in templates.items():
            if not isinstance(tpl, dict):
                continue
            cid = str(tpl.get("category_id") or "").strip()
            if not cid:
                continue
            out.setdefault(cid, []).append(str(tpl.get("id") or tid))
    legacy_map = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    for cid, tids in (legacy_map or {}).items():
        if not isinstance(tids, list):
            continue
        for tid in tids:
            tid_s = str(tid or "").strip()
            if tid_s:
                out.setdefault(str(cid), []).append(tid_s)
    single_map = db.get("category_to_template") if isinstance(db.get("category_to_template"), dict) else {}
    for cid, tid in (single_map or {}).items():
        tid_s = str(tid or "").strip()
        if tid_s:
            out.setdefault(str(cid), []).append(tid_s)
    for cid, tids in out.items():
        uniq: List[str] = []
        seen: set[str] = set()
        for tid in tids:
            if tid in seen:
                continue
            seen.add(tid)
            uniq.append(tid)
        out[cid] = uniq
    return out


def _resolve_competitor_template_for_category(
    category_id: str,
    templates_by_category: Dict[str, List[str]],
    parent_by_id: Dict[str, str],
) -> Tuple[Optional[str], Optional[str]]:
    cid = str(category_id or "").strip()
    if not cid:
        return None, None
    cur = cid
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        tids = templates_by_category.get(cur) or []
        if tids:
            return str(tids[0]), cur
        cur = parent_by_id.get(cur, "")
    return None, None


def _build_competitor_states(catalog_nodes: List[Dict[str, Any]], catalog_items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    from app.storage.json_store import load_competitor_mapping_db

    db = load_competitor_mapping_db()
    category_rows = db.get("categories") if isinstance(db.get("categories"), dict) else {}
    template_rows = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    templates_by_category = _competitor_templates_by_category()
    parent_by_id = _catalog_parent_map(catalog_nodes)

    out: Dict[str, Dict[str, Any]] = {}
    for item in catalog_items:
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue

        row = category_rows.get(cid)
        links = {"restore": "", "store77": ""}
        mapping_by_site = {"restore": {}, "store77": {}}
        if isinstance(row, dict):
            raw_links = row.get("links") if isinstance(row.get("links"), dict) else {}
            links = {
                "restore": str((raw_links or {}).get("restore") or "").strip(),
                "store77": str((raw_links or {}).get("store77") or "").strip(),
            }
            raw_maps = row.get("mapping_by_site") if isinstance(row.get("mapping_by_site"), dict) else {}
            mapping_by_site = {
                "restore": dict(raw_maps.get("restore") or {}) if isinstance(raw_maps.get("restore"), dict) else {},
                "store77": dict(raw_maps.get("store77") or {}) if isinstance(raw_maps.get("store77"), dict) else {},
            }

        has_custom = bool(links["restore"] or links["store77"] or mapping_by_site["restore"] or mapping_by_site["store77"])
        effective_row = {"links": links, "mapping_by_site": mapping_by_site}
        template_id: Optional[str] = None
        source_category_id: Optional[str] = None
        if not has_custom:
            template_id, source_category_id = _resolve_competitor_template_for_category(cid, templates_by_category, parent_by_id)
            if template_id and isinstance(template_rows.get(template_id), dict):
                tpl = template_rows.get(template_id)
                raw_links = tpl.get("links") if isinstance(tpl.get("links"), dict) else {}
                raw_maps = tpl.get("mapping_by_site") if isinstance(tpl.get("mapping_by_site"), dict) else {}
                effective_row = {
                    "links": {
                        "restore": str((raw_links or {}).get("restore") or "").strip(),
                        "store77": str((raw_links or {}).get("store77") or "").strip(),
                    },
                    "mapping_by_site": {
                        "restore": dict(raw_maps.get("restore") or {}) if isinstance(raw_maps.get("restore"), dict) else {},
                        "store77": dict(raw_maps.get("store77") or {}) if isinstance(raw_maps.get("store77"), dict) else {},
                    },
                }

        out[cid] = {
            "configured": _competitor_is_configured_row(effective_row),
            "template_id": template_id or None,
            "source_category_id": source_category_id or None,
            "inherited": bool(source_category_id and source_category_id != cid),
            "links": dict(effective_row.get("links") or {}),
            "mapping_counts": {
                "restore": len((effective_row.get("mapping_by_site") or {}).get("restore") or {}),
                "store77": len((effective_row.get("mapping_by_site") or {}).get("store77") or {}),
            },
        }
    return out


@router.post("/import/categories/link")
def mapping_link_category(req: LinkCategoryReq) -> Dict[str, Any]:
    catalog_id = str(req.catalog_category_id or "").strip()
    provider = str(req.provider or "").strip()
    provider_category_id = str(req.provider_category_id or "").strip()

    if not catalog_id:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if not provider:
        raise HTTPException(status_code=400, detail="PROVIDER_REQUIRED")

    catalog_ids = {x.get("id") for x in _catalog_rows(_load_catalog_nodes())}
    if catalog_id not in catalog_ids:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    provider_items = _load_provider_categories(provider)
    if not provider_items:
        raise HTTPException(status_code=400, detail="PROVIDER_NOT_CONNECTED")

    if provider_category_id and not _is_provider_category_known_or_validated(provider, provider_category_id, provider_items):
        raise HTTPException(status_code=404, detail="PROVIDER_CATEGORY_NOT_FOUND")

    lock = with_lock("marketplace_category_mapping")
    lock.acquire()
    try:
        items = _load_mappings()
        row = items.get(catalog_id, {})
        if not isinstance(row, dict):
            row = {}
        previous_provider_category_id = str(row.get(provider) or "").strip()

        if provider_category_id:
            row[provider] = provider_category_id
        else:
            row.pop(provider, None)

        if row:
            items[catalog_id] = row
        else:
            items.pop(catalog_id, None)

        nodes = _load_catalog_nodes()
        parent_by_id, children_by_parent = _tree_maps(nodes)

        cleared_catalog_ids: List[str] = []
        if provider_category_id:
            descendant_ids = _descendant_ids(catalog_id, children_by_parent)
            direct_descendant_ids = [
                cid
                for cid in set(descendant_ids)
                if isinstance(items.get(cid), dict) and str((items.get(cid) or {}).get(provider) or "").strip()
            ]
            if direct_descendant_ids and not bool(req.force_clear_descendants):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DESCENDANT_BINDINGS_EXIST",
                        "provider": provider,
                        "catalog_category_id": catalog_id,
                        "descendant_category_ids": sorted(direct_descendant_ids),
                    },
                )
            for cid in set(descendant_ids):
                c_row = items.get(cid)
                if not isinstance(c_row, dict):
                    continue
                if provider in c_row:
                    c_row.pop(provider, None)
                    if c_row:
                        items[cid] = c_row
                    else:
                        items.pop(cid, None)
                    cleared_catalog_ids.append(cid)

        _save_mappings(items)
        _invalidate_import_categories_cache()
        _cache_entry(_attr_categories_cache)["ts"] = 0.0
        _cache_entry(_attr_categories_cache)["payload"] = None
        _cache_entry(_attr_bootstrap_cache)["ts"] = 0.0
        _cache_entry(_attr_bootstrap_cache)["payload"] = None
        _details_cache_bucket().clear()
        _persistent_cache_clear(_attr_categories_cache_path())
        _persistent_cache_clear(_attr_bootstrap_cache_path())
        _persistent_attr_details_cache_clear_all()
        if provider in MAPPING_PROVIDERS and previous_provider_category_id and previous_provider_category_id != provider_category_id:
            _record_category_relink_param_review(
                catalog_category_id=catalog_id,
                provider=provider,
                old_provider_category_id=previous_provider_category_id,
                new_provider_category_id=provider_category_id,
            )
        if provider == "ozon" and provider_category_id:
            _close_mapping_review_issue(catalog_id, provider, "category_needs_reselect")
    finally:
        lock.release()

    return {
        "ok": True,
        "catalog_category_id": catalog_id,
        "provider": provider,
        "provider_category_id": provider_category_id or None,
        "cleared_catalog_category_ids": sorted(set(cleared_catalog_ids)),
        "mappings": items,
    }


@router.post("/import/categories/clear-descendants")
def mapping_clear_descendant_bindings(req: ClearDescendantBindingsReq) -> Dict[str, Any]:
    catalog_id = str(req.catalog_category_id or "").strip()
    provider = str(req.provider or "").strip()
    if not catalog_id:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if not provider:
        raise HTTPException(status_code=400, detail="PROVIDER_REQUIRED")

    catalog_rows = _catalog_rows(_load_catalog_nodes())
    catalog_ids = {x.get("id") for x in catalog_rows}
    if catalog_id not in catalog_ids:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    lock = with_lock("marketplace_category_mapping")
    lock.acquire()
    try:
        items = _load_mappings()
        nodes = _load_catalog_nodes()
        parent_by_id, children_by_parent = _tree_maps(nodes)
        descendant_ids = _descendant_ids(catalog_id, children_by_parent)
        direct_descendant_ids = [
            cid
            for cid in set(descendant_ids)
            if isinstance(items.get(cid), dict) and str((items.get(cid) or {}).get(provider) or "").strip()
        ]
        catalog_name_by_id = {
            str(item.get("id") or ""): str(item.get("name") or "")
            for item in catalog_rows
            if str(item.get("id") or "")
        }
        preserved_template_category_ids: List[str] = []
        if req.preserve_templates and direct_descendant_ids:
            preserved_template_category_ids = _preserve_templates_for_categories(
                direct_descendant_ids,
                items,
                {k: str(v or "") for k, v in parent_by_id.items() if v},
                catalog_name_by_id,
            )

        cleared_catalog_ids: List[str] = []
        for cid in direct_descendant_ids:
            c_row = items.get(cid)
            if not isinstance(c_row, dict):
                continue
            if provider in c_row:
                c_row.pop(provider, None)
                if c_row:
                    items[cid] = c_row
                else:
                    items.pop(cid, None)
                cleared_catalog_ids.append(cid)
        _save_mappings(items)
        _invalidate_import_categories_cache()
        _cache_entry(_attr_categories_cache)["ts"] = 0.0
        _cache_entry(_attr_categories_cache)["payload"] = None
        _cache_entry(_attr_bootstrap_cache)["ts"] = 0.0
        _cache_entry(_attr_bootstrap_cache)["payload"] = None
        _details_cache_bucket().clear()
        _persistent_cache_clear(_attr_categories_cache_path())
        _persistent_cache_clear(_attr_bootstrap_cache_path())
        _persistent_attr_details_cache_clear_all()
    finally:
        lock.release()

    return {
        "ok": True,
        "catalog_category_id": catalog_id,
        "provider": provider,
        "cleared_catalog_category_ids": sorted(set(cleared_catalog_ids)),
        "preserved_template_category_ids": preserved_template_category_ids,
        "mappings": items,
    }


@router.get("/import/attributes/categories")
def mapping_attribute_categories() -> Dict[str, Any]:
    now = time.monotonic()
    cache_entry = _cache_entry(_attr_categories_cache)
    cached_payload = cache_entry.get("payload")
    cached_ts = float(cache_entry.get("ts") or 0.0)
    if cached_payload and now - cached_ts < _ATTR_CATEGORIES_CACHE_TTL_SECONDS:
        return cached_payload
    persisted = _persistent_cache_read(_attr_categories_cache_path(), _ATTR_CATEGORIES_CACHE_TTL_SECONDS)
    if persisted:
        cache_entry["ts"] = now
        cache_entry["payload"] = persisted
        return persisted

    _migrate_mapping_documents_to_canonical_names()
    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    by_catalog_id: Dict[str, Dict[str, Any]] = {}
    for c in catalog_items:
        cid = str(c.get("id") or "").strip()
        if cid:
            by_catalog_id[cid] = c
    mappings = _load_mappings()
    doc = _load_attr_mapping_doc()
    rows_doc = doc.get("items") if isinstance(doc.get("items"), dict) else {}

    # Only direct mapping nodes (no inherited children) are shown in this list.
    direct_rows: List[Dict[str, Any]] = []
    for cid, row in mappings.items():
        catalog_id = str(cid or "").strip()
        if not catalog_id:
            continue
        crow = by_catalog_id.get(catalog_id)
        if not crow:
            continue
        m = row if isinstance(row, dict) else {}
        mapping_payload = {
            provider: str(m.get(provider) or "").strip()
            for provider in MAPPING_PROVIDERS
            if str(m.get(provider) or "").strip()
        }
        if not mapping_payload:
            continue
        direct_rows.append(
            {
                "id": catalog_id,
                "name": crow.get("name"),
                "path": crow.get("path"),
                "mapping": mapping_payload,
            }
        )

    direct_rows.sort(key=lambda x: str(x.get("path") or "").lower())

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in direct_rows:
        m = row.get("mapping") if isinstance(row.get("mapping"), dict) else {}
        parts = [f"{provider}:{str(m.get(provider) or '').strip()}" for provider in MAPPING_PROVIDERS if str(m.get(provider) or "").strip()]
        gkey = "|".join(parts)
        grouped.setdefault(gkey, []).append(row)

    out: List[Dict[str, Any]] = []
    for rows in grouped.values():
        if not rows:
            continue
        rows_sorted = sorted(
            rows,
            key=lambda x: (
                str(x.get("path") or "").count("/"),
                len(str(x.get("path") or "")),
                str(x.get("path") or "").lower(),
            ),
        )
        primary = rows_sorted[0]
        group_ids = [str(x.get("id") or "") for x in rows_sorted if str(x.get("id") or "")]
        saved = rows_doc.get(primary.get("id")) if isinstance(rows_doc.get(primary.get("id")), dict) else {}
        rows = _normalize_attr_rows(saved.get("rows") if isinstance(saved, dict) else [])
        total = len(rows)
        done = len([r for r in rows if r.get("confirmed")])
        status = "new" if total == 0 else ("ok" if done == total else "warn")
        out.append(
            {
                "id": primary.get("id"),
                "name": primary.get("name"),
                "path": primary.get("path"),
                "mapping": primary.get("mapping") or {},
                "rows_total": total,
                "rows_confirmed": done,
                "status": status,
                "group_size": len(group_ids),
                "group_extra_count": max(0, len(group_ids) - 1),
                "group_category_ids": group_ids,
            }
        )
    out.sort(key=lambda x: str(x.get("path") or "").lower())
    payload = {"ok": True, "items": out, "count": len(out)}
    cache_entry["ts"] = now
    cache_entry["payload"] = payload
    _persistent_cache_write(_attr_categories_cache_path(), payload)
    return payload


@router.get("/import/attributes/{catalog_category_id}")
def mapping_attribute_details(catalog_category_id: str) -> Dict[str, Any]:
    _migrate_mapping_documents_to_canonical_names()
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")

    details_cache = _details_cache_bucket()
    cached = _timed_cache_get(details_cache, cid, _ATTR_DETAILS_CACHE_TTL_SECONDS)
    if cached:
        return cached
    persisted = _persistent_cache_read(_attr_details_cache_path(cid), _ATTR_DETAILS_CACHE_TTL_SECONDS)
    if persisted:
        _timed_cache_set(
            details_cache,
            cid,
            persisted,
            max_items=_ATTR_DETAILS_CACHE_MAX_ITEMS,
            ttl_seconds=_ATTR_DETAILS_CACHE_TTL_SECONDS,
        )
        return persisted

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    parent_by_id = _catalog_parent_map(catalog_nodes)
    _, children_by_parent = _tree_maps(catalog_nodes)
    catalog_by_id = {str(x.get("id") or ""): x for x in catalog_items}
    cat = next((x for x in catalog_items if str(x.get("id")) == cid), None)
    if not cat:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    mappings = _load_mappings()
    direct_mapping = _direct_mapping_for_catalog(cid, mappings)
    cat_mapping = _effective_mapping_for_catalog(cid, mappings, parent_by_id)
    if not cat_mapping:
        raise HTTPException(status_code=400, detail="CATEGORY_NOT_DIRECTLY_MAPPED")
    mapping_sources = _effective_mapping_sources_for_catalog(cid, mappings, parent_by_id)
    inherited_mapping = any(source and source != cid for source in mapping_sources.values())

    yandex_cat_id = str(cat_mapping.get("yandex_market") or "").strip()
    yandex_cached = _has_yandex_params_cached(yandex_cat_id)
    yandex_params = _load_yandex_params(yandex_cat_id)
    yandex_cat_name = _provider_category_name("yandex_market", yandex_cat_id)
    ozon_cat_id = str(cat_mapping.get("ozon") or "").strip()
    ozon_cached = _has_ozon_params_cached(ozon_cat_id)
    ozon_params = _load_ozon_params(ozon_cat_id)
    ozon_cat_name = _provider_category_name("ozon", ozon_cat_id)

    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    saved = items.get(cid) if isinstance(items.get(cid), dict) else {}
    rows = _prune_rows_for_current_provider_params(
        saved.get("rows") if isinstance(saved, dict) else [],
        yandex_params,
        ozon_params,
    )
    templates_db = load_templates_db()
    cat_to_tpls = templates_db.get("category_to_templates") if isinstance(templates_db.get("category_to_templates"), dict) else {}
    template_id = ""
    if isinstance(cat_to_tpls, dict):
        tids = cat_to_tpls.get(cid) if isinstance(cat_to_tpls.get(cid), list) else []
        template_id = str((tids or [""])[0] or "").strip()
    template = ((templates_db.get("templates") or {}).get(template_id) if template_id else None) or {}
    template_meta = template.get("meta") if isinstance(template, dict) and isinstance(template.get("meta"), dict) else {}
    catalog_attr_options = _catalog_attr_options_for_category(cid)

    payload = {
        "ok": True,
        "category": {"id": cid, "name": cat.get("name"), "path": cat.get("path")},
        "mapping": cat_mapping,
        "mapping_meta": {
            "direct": direct_mapping,
            "effective": cat_mapping,
            "sources": mapping_sources,
            "inherited": inherited_mapping,
        },
        "providers": {
            "yandex_market": {
                "category_id": yandex_cat_id or None,
                "category_name": yandex_cat_name or None,
                "params": yandex_params,
                "count": len(yandex_params),
                "cached": yandex_cached,
            },
            "ozon": {
                "category_id": ozon_cat_id or None,
                "category_name": ozon_cat_name or None,
                "params": ozon_params,
                "count": len(ozon_params),
                "cached": ozon_cached,
            },
        },
        "rows": rows,
        "suggested_rows": [],
        "suggested_rows_count": 0,
        "updated_at": saved.get("updated_at") if isinstance(saved, dict) else None,
        "template_id": template_id or None,
        "master_template": template_meta.get("master_template") if isinstance(template_meta.get("master_template"), dict) else None,
        "sources": template_meta.get("sources") if isinstance(template_meta.get("sources"), dict) else {},
        "catalog_attr_options": catalog_attr_options,
    }
    _timed_cache_set(
        details_cache,
        cid,
        payload,
        max_items=_ATTR_DETAILS_CACHE_MAX_ITEMS,
        ttl_seconds=_ATTR_DETAILS_CACHE_TTL_SECONDS,
    )
    _persistent_cache_write(_attr_details_cache_path(cid), payload)
    return payload


@router.get("/import/values/{catalog_category_id}")
def mapping_value_details(catalog_category_id: str) -> Dict[str, Any]:
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")

    value_cache = _value_details_cache_bucket()
    cached = _timed_cache_get(value_cache, cid, _VALUE_DETAILS_CACHE_TTL_SECONDS)
    if cached:
        return cached

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    parent_by_id = _catalog_parent_map(catalog_nodes)
    _, children_by_parent = _tree_maps(catalog_nodes)
    catalog_by_id = {str(x.get("id") or ""): x for x in catalog_items}
    cat = next((x for x in catalog_items if str(x.get("id")) == cid), None)
    if not cat:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    values_doc = _load_attr_values_dict_doc()
    items = values_doc.get("items") if isinstance(values_doc.get("items"), dict) else {}
    payload = items.get(cid) if isinstance(items, dict) and isinstance(items.get(cid), dict) else {}
    catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
    if not catalog_params:
        attr_doc = _load_attr_mapping_doc()
        attr_items = attr_doc.get("items") if isinstance(attr_doc.get("items"), dict) else {}
        attr_payload = attr_items.get(cid) if isinstance(attr_items, dict) and isinstance(attr_items.get(cid), dict) else {}
        attr_rows = attr_payload.get("rows") if isinstance(attr_payload.get("rows"), list) else []
        if attr_rows:
            _upsert_attr_values_dictionary_for_category(
                cid,
                attr_rows,
                mappings=_load_mappings(),
                parent_by_id=parent_by_id,
            )
            values_doc = _load_attr_values_dict_doc()
            items = values_doc.get("items") if isinstance(values_doc.get("items"), dict) else {}
            payload = items.get(cid) if isinstance(items, dict) and isinstance(items.get(cid), dict) else {}
            catalog_params = payload.get("catalog_params") if isinstance(payload.get("catalog_params"), dict) else {}
    if not catalog_params and isinstance(items, dict):
        branch_payload = _value_payload_with_descendant_refs(
            catalog_category_id=cid,
            values_items=items,
            children_by_parent=children_by_parent,
            catalog_by_id=catalog_by_id,
        )
        branch_params = branch_payload.get("catalog_params") if isinstance(branch_payload.get("catalog_params"), dict) else {}
        if branch_params:
            payload = branch_payload
            catalog_params = branch_params

    dict_db = load_dictionaries_db()
    dict_items = dict_db.get("items") if isinstance(dict_db.get("items"), list) else []
    dict_by_id = {
        str(d.get("id") or "").strip(): d
        for d in dict_items
        if isinstance(d, dict) and str(d.get("id") or "").strip()
    }

    out: List[Dict[str, Any]] = []
    for raw in catalog_params.values():
        if not isinstance(raw, dict):
            continue
        dict_id = str(raw.get("dict_id") or "").strip()
        if not dict_id:
            continue
        dict_doc = dict_by_id.get(dict_id) or load_dict(dict_id)
        meta = dict_doc.get("meta") if isinstance(dict_doc.get("meta"), dict) else {}
        source_ref = meta.get("source_reference") if isinstance(meta.get("source_reference"), dict) else {}
        export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
        raw_bindings = raw.get("bindings") if isinstance(raw.get("bindings"), dict) else {}
        raw_scope = str(dict_doc.get("scope") or "").strip().lower()
        value_count, pim_sample, pim_values = _dictionary_value_samples(dict_doc)
        if raw_scope == "variant":
            scope = "group"
            scope_label = "Группа"
        elif raw_scope == "both":
            scope = "shared"
            scope_label = "Товар и группа"
        else:
            scope = "product"
            scope_label = "Товар"
        source_category = raw.get("source_category") if isinstance(raw.get("source_category"), dict) else None
        evidence_category_id = str((source_category or {}).get("id") or cid).strip()
        evidence_category_ids = [evidence_category_id] if evidence_category_id else [cid]
        for child_id in _descendant_ids(evidence_category_id, children_by_parent):
            if child_id not in evidence_category_ids:
                evidence_category_ids.append(child_id)
        source_evidence = _feature_source_evidence(
            category_ids=evidence_category_ids,
            catalog_name=str(raw.get("catalog_name") or dict_doc.get("title") or dict_id),
            pim_values=pim_values,
        )

        providers: List[Dict[str, Any]] = []
        for provider in MAPPING_PROVIDERS:
            binding_ref = raw_bindings.get(provider) if isinstance(raw_bindings.get(provider), dict) else {}
            meta_ref = source_ref.get(provider) if isinstance(source_ref.get(provider), dict) else {}
            ref = binding_ref if any(binding_ref.get(k) for k in ("id", "name", "kind", "values")) else meta_ref
            allowed_values = _unique_text_values(ref.get("allowed_values"), limit=200)
            if not allowed_values:
                allowed_values = _unique_text_values(ref.get("values"), limit=200)
            mapped_values = export_map.get(provider) if isinstance(export_map.get(provider), dict) else {}
            if not ref and not allowed_values and not mapped_values:
                continue
            provider_mode = _value_mode_from_type(ref.get("kind"), allowed_values)
            dictionary_quality = _provider_dictionary_quality(allowed_values, value_count)
            coverage = (
                _provider_value_coverage(dict_id, provider, pim_values)
                if provider_mode in {"boolean", "enum", "multi"} and pim_values
                else {"covered_count": 0, "missing_count": 0, "missing_sample": []}
            )
            needs_mapping = provider_mode in {"boolean", "enum", "multi"} and int(coverage.get("missing_count") or 0) > 0
            providers.append(
                {
                    "code": provider,
                    "title": PROVIDER_TITLES.get(provider, provider),
                    "mapped_count": len(mapped_values),
                    "allowed_count": len(allowed_values),
                    "covered_count": int(coverage.get("covered_count") or 0),
                    "missing_count": int(coverage.get("missing_count") or 0),
                    "kind": str(ref.get("kind") or "").strip() or None,
                    "mode": provider_mode,
                    "needs_mapping": needs_mapping,
                    "needs_unit_check": provider_mode == "number",
                    "mapped_sample": [
                        {"canonical": str(k), "output": str(v)}
                        for k, v in list(mapped_values.items())[:4]
                    ],
                    "mapped_values": {
                        str(k): str(v)
                        for k, v in list(mapped_values.items())[:120]
                    },
                    "allowed_sample": allowed_values[:4],
                    "allowed_values": allowed_values[:160],
                    "dictionary_quality": dictionary_quality,
                    "missing_sample": coverage.get("missing_sample") if isinstance(coverage.get("missing_sample"), list) else [],
                    "missing_values": coverage.get("missing_values") if isinstance(coverage.get("missing_values"), list) else [],
                    "param_name": str(ref.get("name") or "").strip() or None,
                    "required": bool(ref.get("required") or False),
                }
            )

        item_type = str(dict_doc.get("type") or raw.get("type") or "").strip() or "select"
        provider_modes = {str(p.get("mode") or "") for p in providers}
        if "boolean" in provider_modes or _value_mode_from_type(item_type) == "boolean":
            value_mode = "boolean"
        elif "number" in provider_modes:
            value_mode = "number"
        elif "multi" in provider_modes:
            value_mode = "multi"
        elif "enum" in provider_modes or _value_mode_from_type(item_type) == "enum":
            value_mode = "enum"
        elif _value_mode_from_type(item_type) == "number":
            value_mode = "number"
        else:
            value_mode = "text"
        needs_value_mapping = any(bool(p.get("needs_mapping")) for p in providers)
        needs_unit_check = any(bool(p.get("needs_unit_check")) for p in providers)
        out.append(
            {
                "dict_id": dict_id,
                "title": str(dict_doc.get("title") or raw.get("catalog_name") or dict_id),
                "catalog_name": str(raw.get("catalog_name") or dict_doc.get("title") or dict_id),
                "group": str(raw.get("group") or meta.get("param_group") or "").strip() or "О товаре",
                "scope": scope,
                "scope_label": scope_label,
                "type": item_type,
                "value_mode": value_mode,
                "confirmed": bool(raw.get("confirmed") or False),
                "attribute_id": str(raw.get("attribute_id") or "").strip() or None,
                "value_count": value_count,
                "pim_sample": pim_sample,
                "pim_values": pim_values[:80],
                "source_evidence": source_evidence,
                "needs_value_mapping": needs_value_mapping,
                "needs_unit_check": needs_unit_check,
                "source_category": source_category,
                "providers": providers,
                "providers_count": len(providers),
                "mapped_total": sum(int(p.get("mapped_count") or 0) for p in providers),
            }
        )

    out.sort(key=lambda x: (str(x.get("group") or "").lower(), str(x.get("catalog_name") or "").lower()))
    result = {
        "ok": True,
        "category": {"id": cid, "name": cat.get("name"), "path": cat.get("path")},
        "items": out,
        "count": len(out),
        "branch_sources": payload.get("branch_sources") if isinstance(payload.get("branch_sources"), list) else [],
    }
    _timed_cache_set(
        value_cache,
        cid,
        result,
        max_items=_VALUE_DETAILS_CACHE_MAX_ITEMS,
        ttl_seconds=_VALUE_DETAILS_CACHE_TTL_SECONDS,
    )
    return result


@router.post("/import/values/{catalog_category_id}/dictionaries/{dict_id}/ai-suggest")
async def mapping_value_ai_suggest(catalog_category_id: str, dict_id: str, req: ValueAiSuggestReq) -> Dict[str, Any]:
    require_ai_enabled()

    cid = str(catalog_category_id or "").strip()
    did = str(dict_id or "").strip()
    provider = str(req.provider or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if not did:
        raise HTTPException(status_code=400, detail="DICT_ID_REQUIRED")
    if provider not in set(MAPPING_PROVIDERS):
        raise HTTPException(status_code=400, detail="PROVIDER_INVALID")

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    if not any(str(item.get("id") or "") == cid for item in catalog_items):
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    doc = load_dict(did)
    pim_values = _dictionary_values(doc)
    dictionary_allowed_values = _provider_allowed_values(doc, provider)
    category_allowed_values: List[str] = []
    allowed_values = dictionary_allowed_values
    if not allowed_values:
        category_allowed_values = _provider_allowed_values_for_category_dict(cid, did, provider)
        allowed_values = category_allowed_values
    if not pim_values:
        return {
            "ok": True,
            "applied": False,
            "provider": provider,
            "dict_id": did,
            "suggestions": [],
            "summary": {"pim_values": 0, "allowed_values": len(allowed_values), "suggestions": 0, "engine": "none"},
            "message": "В PIM-словаре пока нет значений для сопоставления.",
        }
    if not allowed_values:
        return {
            "ok": True,
            "applied": False,
            "provider": provider,
            "dict_id": did,
            "suggestions": [],
            "summary": {"pim_values": len(pim_values), "allowed_values": 0, "suggestions": 0, "engine": "none"},
            "message": "У площадки нет справочника значений для этого поля.",
        }

    existing_map = _current_export_map(doc, provider)
    missing_values: List[str] = []
    for value in pim_values:
        key = normalize_value_key(value)
        existing_output = existing_map.get(key)
        if existing_output and _mapped_export_value_is_allowed(existing_output, allowed_values):
            continue
        if dictionary_allowed_values:
            details = provider_export_value_details(did, provider, value)
            output_value = str(details.get("value") or "").strip()
            if bool(details.get("mapped", True)) and _mapped_export_value_is_allowed(output_value, allowed_values):
                continue
        missing_values.append(value)
    if not missing_values:
        return {
            "ok": True,
            "applied": False,
            "provider": provider,
            "dict_id": did,
            "suggestions": [],
            "summary": {
                "pim_values": len(pim_values),
                "allowed_values": len(allowed_values),
                "suggestions": 0,
                "engine": "already_covered",
            },
            "message": "Все PIM-значения уже покрыты для этой площадки.",
        }

    deterministic = _deterministic_value_suggestions(missing_values, allowed_values)
    deterministic_valid = _validated_value_suggestions(
        raw_pairs=deterministic,
        pim_values=missing_values,
        allowed_values=allowed_values,
        source="rule",
    )
    ai_valid: List[Dict[str, Any]] = []
    ai_error = ""
    try:
        async with asyncio.timeout(_ai_match_timeout_seconds()):
            ai_raw = await _ollama_suggest_value_pairs(
                dict_title=str(doc.get("title") or did),
                provider=provider,
                pim_values=missing_values,
                allowed_values=allowed_values,
            )
        ai_valid = _validated_value_suggestions(
            raw_pairs=ai_raw,
            pim_values=missing_values,
            allowed_values=allowed_values,
            source="ollama",
        )
    except Exception as exc:
        ai_error = f"{exc.__class__.__name__}: {str(exc).strip()}"[:240]

    by_key: Dict[str, Dict[str, Any]] = {}
    for suggestion in deterministic_valid + ai_valid:
        key = normalize_value_key(suggestion.get("canonical"))
        if not key:
            continue
        prev = by_key.get(key)
        if not prev or str(suggestion.get("source")) == "ollama" or float(suggestion.get("confidence") or 0) > float(prev.get("confidence") or 0):
            by_key[key] = suggestion
    suggestions = list(by_key.values())

    applied = False
    if req.apply and suggestions:
        doc = _apply_value_suggestions_to_dict(doc, provider, suggestions)
        applied = True
        _value_details_cache_bucket().pop(cid, None)

    return {
        "ok": True,
        "applied": applied,
        "provider": provider,
        "dict_id": did,
        "suggestions": suggestions,
        "summary": {
            "pim_values": len(pim_values),
            "missing_values": len(missing_values),
            "allowed_values": len(allowed_values),
            "suggestions": len(suggestions),
            "engine": "ollama" if ai_valid else "rule",
            "rule_suggestions": len(deterministic_valid),
            "ai_suggestions": len(ai_valid),
        },
        "ai_error": ai_error,
        "item": doc if applied else None,
    }


@router.post("/import/values/{catalog_category_id}/dictionaries/{dict_id}/ai-suggest/jobs")
async def mapping_value_ai_suggest_job_start(catalog_category_id: str, dict_id: str, req: ValueAiSuggestReq) -> Dict[str, Any]:
    require_ai_enabled()

    cid = str(catalog_category_id or "").strip()
    did = str(dict_id or "").strip()
    provider = str(req.provider or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if not did:
        raise HTTPException(status_code=400, detail="DICT_ID_REQUIRED")
    if provider not in set(MAPPING_PROVIDERS):
        raise HTTPException(status_code=400, detail="PROVIDER_INVALID")

    _prune_value_ai_jobs()
    for job in list_pim_workflow_runs(workflow=_VALUE_AI_WORKFLOW, statuses=["queued", "running"], limit=100):
        if (
            str(job.get("catalog_category_id") or "") == cid
            and str(job.get("dict_id") or "") == did
            and str(job.get("provider") or "") == provider
            and str(job.get("status") or "") in {"queued", "running"}
        ):
            return _public_value_ai_job(job)

    job_id = f"value_ai_job_{uuid4().hex}"
    job = {
        "id": job_id,
        "run_id": job_id,
        "job_id": job_id,
        "catalog_category_id": cid,
        "dict_id": did,
        "provider": provider,
        "status": "queued",
        "phase": "queued",
        "message": "Автоподбор значений поставлен в очередь.",
        "created_at": _now_iso(),
        "created_ts": time.time(),
        "updated_ts": time.time(),
        "apply": bool(req.apply),
    }
    _save_value_ai_job(job)
    return _public_value_ai_job(job)


@router.get("/import/values/ai-suggest/jobs/{job_id}")
async def mapping_value_ai_suggest_job_status(job_id: str) -> Dict[str, Any]:
    require_ai_enabled()

    _prune_value_ai_jobs()
    jid = str(job_id or "").strip()
    job = get_pim_workflow_run(jid, workflow=_VALUE_AI_WORKFLOW)
    if not job:
        raise HTTPException(status_code=404, detail="VALUE_AI_MATCH_JOB_NOT_FOUND")
    return _public_value_ai_job(job)


@router.patch("/import/values/{catalog_category_id}/dictionaries/{dict_id}/export-map")
def mapping_value_export_map_patch(catalog_category_id: str, dict_id: str, req: ValueExportMapPatchReq) -> Dict[str, Any]:
    cid = str(catalog_category_id or "").strip()
    did = str(dict_id or "").strip()
    provider = str(req.provider or "").strip()
    canonical_value = str(req.canonical_value or "").strip()
    output_value = str(req.output_value or "").strip() if req.output_value is not None else ""
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    if not did:
        raise HTTPException(status_code=400, detail="DICT_ID_REQUIRED")
    if provider not in set(MAPPING_PROVIDERS):
        raise HTTPException(status_code=400, detail="PROVIDER_INVALID")
    if not canonical_value:
        raise HTTPException(status_code=400, detail="CANONICAL_VALUE_REQUIRED")

    doc = load_dict(did)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    export_map = meta.get("export_map") if isinstance(meta.get("export_map"), dict) else {}
    provider_map = export_map.get(provider) if isinstance(export_map.get(provider), dict) else {}
    provider_map = {
        normalize_value_key(str(key or "")): str(value or "").strip()
        for key, value in provider_map.items()
        if normalize_value_key(str(key or "")) and str(value or "").strip()
    }
    key = normalize_value_key(canonical_value)
    if output_value:
        provider_map[key] = output_value
    else:
        provider_map.pop(key, None)
    if provider_map:
        export_map[provider] = provider_map
    else:
        export_map.pop(provider, None)
    meta["export_map"] = export_map
    doc["meta"] = meta
    doc["updated_at"] = _now_iso()
    save_dict(doc)
    _value_details_cache_bucket().pop(cid, None)
    return {"ok": True, "item": doc}


@router.put("/import/attributes/{catalog_category_id}")
def mapping_attribute_save(catalog_category_id: str, req: SaveAttrMappingReq) -> Dict[str, Any]:
    _migrate_mapping_documents_to_canonical_names()
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    _cache_entry(_attr_categories_cache)["ts"] = 0.0
    _cache_entry(_attr_categories_cache)["payload"] = None
    _cache_entry(_attr_bootstrap_cache)["ts"] = 0.0
    _cache_entry(_attr_bootstrap_cache)["payload"] = None
    _details_cache_bucket().pop(cid, None)
    _value_details_cache_bucket().pop(cid, None)
    _persistent_cache_clear(_attr_categories_cache_path())
    _persistent_cache_clear(_attr_bootstrap_cache_path())
    _persistent_cache_clear(_attr_details_cache_path(cid))

    catalog_rows = _catalog_rows(_load_catalog_nodes())
    catalog_ids = {x.get("id") for x in catalog_rows}
    catalog_name_by_id = {str(x.get("id") or ""): str(x.get("name") or "") for x in catalog_rows}
    if cid not in catalog_ids:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    mappings = _load_mappings()
    parent_by_id = _catalog_parent_map(_load_catalog_nodes())

    lock = with_lock("marketplace_attribute_mapping")
    lock.acquire()
    try:
        doc = _load_attr_mapping_doc()
        items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
        if not isinstance(items, dict):
            items = {}
        prev_saved = items.get(cid) if isinstance(items.get(cid), dict) else {}
        prev_rows = _normalize_attr_rows(prev_saved.get("rows") if isinstance(prev_saved, dict) else [])

        rows_in = [r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in (req.rows or [])]
        rows = _normalize_attr_rows(rows_in)
        apply_ids: List[str] = [cid]
        for raw_id in req.apply_to_category_ids or []:
            xid = str(raw_id or "").strip()
            if xid and xid in catalog_ids and xid not in apply_ids:
                apply_ids.append(xid)

        saved_ids: List[str] = []
        for xid in apply_ids:
            items[xid] = {"rows": rows, "updated_at": _now_iso()}
            saved_ids.append(xid)
            _upsert_template_from_attr_mapping(
                xid,
                rows,
                catalog_name_by_id.get(xid) or xid,
                mappings=mappings,
                parent_by_id=parent_by_id,
            )
            _upsert_attr_values_dictionary_for_category(
                xid,
                rows,
                mappings=mappings,
                parent_by_id=parent_by_id,
            )
        doc["items"] = items
        save_attribute_mapping_doc(doc)
    finally:
        lock.release()

    _record_feedback_from_rows(prev_rows, rows)
    templates_db = load_templates_db()
    cat_to_tpls = templates_db.get("category_to_templates") if isinstance(templates_db.get("category_to_templates"), dict) else {}
    template_id = ""
    if isinstance(cat_to_tpls, dict):
        tids = cat_to_tpls.get(cid) if isinstance(cat_to_tpls.get(cid), list) else []
        template_id = str((tids or [""])[0] or "").strip()
    template = ((templates_db.get("templates") or {}).get(template_id) if template_id else None) or {}
    template_meta = template.get("meta") if isinstance(template, dict) and isinstance(template.get("meta"), dict) else {}
    return {
        "ok": True,
        "catalog_category_id": cid,
        "rows_count": len(rows),
        "saved_category_ids": saved_ids,
        "template_id": template_id or None,
        "master_template": template_meta.get("master_template") if isinstance(template_meta.get("master_template"), dict) else None,
        "sources": template_meta.get("sources") if isinstance(template_meta.get("sources"), dict) else {},
    }


@router.post("/import/attributes/{catalog_category_id}/ai-match")
async def mapping_attribute_ai_match(catalog_category_id: str, req: AiMatchReq) -> Dict[str, Any]:
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    parent_by_id = _catalog_parent_map(catalog_nodes)
    cat = next((x for x in catalog_items if str(x.get("id")) == cid), None)
    if not cat:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    mappings = _load_mappings()
    cat_mapping = _effective_mapping_for_catalog(cid, mappings, parent_by_id)
    if not cat_mapping:
        raise HTTPException(status_code=400, detail="CATEGORY_NOT_DIRECTLY_MAPPED")

    yandex_cat_id = str(cat_mapping.get("yandex_market") or "").strip()
    yandex_params = _load_yandex_params(yandex_cat_id)
    ozon_cat_id = str(cat_mapping.get("ozon") or "").strip()
    ozon_params = _load_ozon_params(ozon_cat_id)

    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not isinstance(items, dict):
        items = {}
    saved = items.get(cid) if isinstance(items.get(cid), dict) else {}
    existing_rows = _prune_rows_for_current_provider_params(
        saved.get("rows") if isinstance(saved, dict) else [],
        yandex_params,
        ozon_params,
    )
    catalog_attr_options = _catalog_attr_options_for_category(cid)
    if not catalog_attr_options:
        catalog_attr_options = _provider_param_target_options(yandex_params, ozon_params)
    target_rows = _catalog_target_rows(catalog_attr_options, _service_param_defs_payload())
    seed_rows = _merge_existing_into_target_rows(target_rows, existing_rows)
    feedback_doc = _load_attr_feedback_doc()

    rows_ai: Optional[List[Dict[str, Any]]] = None
    engine = "fallback"
    ai_error = ""
    ai_seed_rows = [
        row
        for row in seed_rows
        if not str((((row.get("provider_map") or {}).get("yandex_market") or {}).get("id") or "")).strip()
    ]
    try:
        if ai_enabled() and ai_seed_rows:
            async with asyncio.timeout(_ai_match_timeout_seconds()):
                rows_ai = await _ollama_suggest_rows_chunked(
                    category_name=str(cat.get("path") or cat.get("name") or cid),
                    yandex_params=yandex_params,
                    existing_rows=ai_seed_rows,
                    feedback_doc=feedback_doc,
                )
        if rows_ai:
            rows_ai = _merge_ai_rows_into_target_rows(seed_rows, rows_ai)
            rows_ai = _deterministic_ai_rows(
                [],
                rows_ai,
                feedback_doc=feedback_doc,
                ozon_params=ozon_params,
            )
            engine = "ollama"
    except Exception as exc:
        ai_error = f"{exc.__class__.__name__}: {str(exc).strip()}"[:240]
        rows_ai = None

    rows_final = rows_ai or _deterministic_ai_rows(
        yandex_params,
        seed_rows,
        feedback_doc=feedback_doc,
        ozon_params=ozon_params,
    )
    rows_final = _fill_missing_provider_metadata_from_memory(rows_final, seed_rows)
    rows_final = _clear_core_export_provider_bindings(rows_final)
    rows_final = _apply_group_locks(rows_final)
    run_summary = _attr_ai_run_summary(seed_rows, rows_final)

    if req.apply:
        _cache_entry(_attr_categories_cache)["ts"] = 0.0
        _cache_entry(_attr_categories_cache)["payload"] = None
        _cache_entry(_attr_bootstrap_cache)["ts"] = 0.0
        _cache_entry(_attr_bootstrap_cache)["payload"] = None
        _details_cache_bucket().pop(cid, None)
        _value_details_cache_bucket().pop(cid, None)
        _persistent_cache_clear(_attr_categories_cache_path())
        _persistent_cache_clear(_attr_bootstrap_cache_path())
        _persistent_cache_clear(_attr_details_cache_path(cid))
        lock = with_lock("marketplace_attribute_mapping")
        lock.acquire()
        try:
            doc_apply = _load_attr_mapping_doc()
            doc_items = doc_apply.get("items") if isinstance(doc_apply.get("items"), dict) else {}
            if not isinstance(doc_items, dict):
                doc_items = {}
            doc_items[cid] = {"rows": rows_final, "updated_at": _now_iso()}
            doc_apply["items"] = doc_items
            save_attribute_mapping_doc(doc_apply)
            _upsert_template_from_attr_mapping(
                cid,
                rows_final,
                str(cat.get("name") or cid),
                mappings=mappings,
                parent_by_id=parent_by_id,
            )
            _upsert_attr_values_dictionary_for_category(
                cid,
                rows_final,
                mappings=mappings,
                parent_by_id=parent_by_id,
            )
        finally:
            lock.release()
        _record_feedback_from_rows(existing_rows, rows_final)

    return {
        "ok": True,
        "catalog_category_id": cid,
        "engine": engine,
        "applied": bool(req.apply),
        "rows": rows_final,
        "rows_count": len(rows_final),
        "summary": run_summary,
        "ai_error": ai_error,
    }


@router.post("/import/attributes/{catalog_category_id}/ai-match/jobs")
async def mapping_attribute_ai_match_job_start(catalog_category_id: str, req: AiMatchReq) -> Dict[str, Any]:
    require_ai_enabled()

    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")

    _prune_attr_ai_jobs()
    for job in list_pim_workflow_runs(workflow=_ATTR_AI_WORKFLOW, statuses=["queued", "running"], limit=100):
        if (
            str(job.get("catalog_category_id") or "") == cid
            and str(job.get("status") or "") in {"queued", "running"}
        ):
            return _public_attr_ai_job(job)

    job_id = f"attr_ai_job_{uuid4().hex}"
    job = {
        "id": job_id,
        "run_id": job_id,
        "job_id": job_id,
        "catalog_category_id": cid,
        "status": "queued",
        "phase": "queued",
        "message": "Автоподбор поставлен в очередь.",
        "created_at": _now_iso(),
        "created_ts": time.time(),
        "updated_ts": time.time(),
        "apply": bool(req.apply),
    }
    _save_attr_ai_job(job)
    return _public_attr_ai_job(job)


@router.get("/import/attributes/ai-match/jobs/{job_id}")
async def mapping_attribute_ai_match_job_status(job_id: str) -> Dict[str, Any]:
    require_ai_enabled()

    _prune_attr_ai_jobs()
    jid = str(job_id or "").strip()
    job = get_pim_workflow_run(jid, workflow=_ATTR_AI_WORKFLOW)
    if not job:
        raise HTTPException(status_code=404, detail="AI_MATCH_JOB_NOT_FOUND")
    return _public_attr_ai_job(job)
