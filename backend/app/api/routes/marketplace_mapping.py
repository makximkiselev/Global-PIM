from __future__ import annotations

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

from app.core.json_store import read_doc, write_doc, with_lock
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

MAPPINGS_PATH = MARKETPLACES_DIR / "category_mapping.json"
ATTR_MAPPING_PATH = MARKETPLACES_DIR / "attribute_master_mapping.json"
ATTR_VALUES_DICT_PATH = MARKETPLACES_DIR / "attribute_value_dictionary.json"
CATALOG_NODES_PATH = DATA_DIR / "catalog_nodes.json"
YANDEX_CATEGORY_PARAMS_PATH = MARKETPLACES_DIR / "yandex_market" / "category_parameters.json"
OZON_CATEGORY_ATTRS_PATH = MARKETPLACES_DIR / "ozon" / "category_attributes.json"
ATTR_FEEDBACK_PATH = MARKETPLACES_DIR / "attribute_match_feedback.json"

PROVIDER_TITLES: Dict[str, str] = {
    "yandex_market": "Я.Маркет",
    "ozon": "Ozon",
}

MAPPING_PROVIDERS: tuple[str, ...] = tuple(PROVIDER_TITLES.keys())

DEFAULT_SERVICE_NAMES: List[str] = [str(item["name"]) for item in base_template_fields()]
_ATTR_CATEGORIES_CACHE_TTL_SECONDS = 30.0
_ATTR_DETAILS_CACHE_TTL_SECONDS = 30.0
_attr_categories_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
_attr_details_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def _load_catalog_nodes() -> List[Dict[str, Any]]:
    doc = read_doc(CATALOG_NODES_PATH, default=[])
    return doc if isinstance(doc, list) else []


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


def _load_mappings() -> Dict[str, Dict[str, str]]:
    doc = read_doc(MAPPINGS_PATH, default={"version": 1, "items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}

    out: Dict[str, Dict[str, str]] = {}
    for catalog_id, m in items.items():
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
    write_doc(MAPPINGS_PATH, {"version": 1, "items": items})


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_attr_mapping_doc() -> Dict[str, Any]:
    doc = read_doc(ATTR_MAPPING_PATH, default={"version": 1, "items": {}})
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    return doc


def _load_attr_values_dict_doc() -> Dict[str, Any]:
    doc = read_doc(ATTR_VALUES_DICT_PATH, default={"version": 2, "updated_at": None, "items": {}})
    if not isinstance(doc, dict):
        doc = {"version": 2, "updated_at": None, "items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    if not isinstance(doc.get("version"), int) or int(doc.get("version") or 0) < 2:
        doc["version"] = 2
    return doc


def _save_attr_values_dict_doc(doc: Dict[str, Any]) -> None:
    doc["updated_at"] = _now_iso()
    write_doc(ATTR_VALUES_DICT_PATH, doc)


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

    doc = _load_attr_values_dict_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not isinstance(items, dict):
        items = {}
    items[cid] = {
        "catalog_category_id": cid,
        "providers": providers_payload,
        "catalog_params": by_catalog_name,
        "rows_count": len(norm_rows),
        "updated_at": _now_iso(),
    }
    doc["items"] = items
    _save_attr_values_dict_doc(doc)


def _catalog_param_group_locks() -> Dict[str, str]:
    """
    Lock map: catalog parameter title -> param_group from /data/dictionaries.json.
    Apply only for parameters with explicit type, as requested by product logic.
    """
    doc = read_doc(DATA_DIR / "dictionaries.json", default={"items": []})
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
                pmap[provider] = {"id": "", "name": "", "kind": "", "values": [], "required": False, "export": False}
                continue
            pmap[provider] = {
                "id": str(cur.get("id") or "").strip(),
                "name": str(cur.get("name") or "").strip(),
                "kind": str(cur.get("kind") or "").strip(),
                "values": _extract_text_list(cur.get("values"))[:200],
                "required": bool(cur.get("required") or False),
                "export": bool(cur.get("export") or False),
            }
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
            if not str(cur_payload.get("id") or "").strip() and (
                str(row_payload.get("id") or "").strip() or str(row_payload.get("name") or "").strip()
            ):
                cur_map[provider] = row_payload
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
        write_doc(ATTR_MAPPING_PATH, doc)

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
    save_templates_db(db)


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


@router.get("/import/categories")
def mapping_import_categories() -> Dict[str, Any]:
    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    mappings = _load_mappings()
    binding_states = _build_binding_states(catalog_nodes, catalog_items, mappings)

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

    return {
        "ok": True,
        "catalog_nodes": catalog_nodes,
        "catalog_items": catalog_items,
        "providers": providers,
        "provider_categories": provider_categories,
        "mappings": mappings,
        "binding_states": binding_states,
    }


class LinkCategoryReq(BaseModel):
    catalog_category_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_category_id: Optional[str] = None
    force_clear_descendants: bool = False


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


class AttrRowProviderMap(BaseModel):
    id: str = ""
    name: str = ""
    kind: str = ""
    values: List[str] = Field(default_factory=list)
    required: bool = False
    export: bool = False


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
    yt = _tokens(str(y.get("name") or ""))
    ot = _tokens(str(o.get("name") or ""))
    if not yt or not ot:
        return 0.0
    inter = len(yt & ot)
    union = max(1, len(yt | ot))
    j = inter / union
    y_name = _norm_name(str(y.get("name") or ""))
    o_name = _norm_name(str(o.get("name") or ""))
    sub = 0.2 if (y_name and o_name and (y_name in o_name or o_name in y_name)) else 0.0
    kind_bonus = 0.1 if _kind_group(str(y.get("kind") or "")) == _kind_group(str(o.get("kind") or "")) else 0.0
    feedback = _feedback_bonus(y, o, feedback_doc)
    return j + sub + kind_bonus + feedback


def _service_names() -> List[str]:
    dpath = DATA_DIR / "dictionaries.json"
    doc = read_doc(dpath, default={"items": []})
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
    return {"id": "", "name": "", "kind": "", "values": [], "required": False, "export": False}


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
            },
            "ozon": {
                "id": str((oz or {}).get("id") or "").strip(),
                "name": oz_name,
                "kind": str((oz or {}).get("kind") or "").strip(),
                "values": _extract_text_list((oz or {}).get("values")),
                "required": bool((oz or {}).get("required") or False),
                "export": bool(oz),
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


def _collect_template_rows_from_saved(
    attr_doc: Dict[str, Any],
    exclude_category_id: str,
    limit: int = 240,
) -> List[Dict[str, Any]]:
    items = attr_doc.get("items") if isinstance(attr_doc.get("items"), dict) else {}
    if not isinstance(items, dict):
        return []
    out: List[Dict[str, Any]] = []
    for cid, payload in items.items():
        if str(cid or "").strip() == str(exclude_category_id or "").strip():
            continue
        row_list = _normalize_attr_rows(payload.get("rows") if isinstance(payload, dict) else [])
        for r in row_list:
            pmap = r.get("provider_map") if isinstance(r.get("provider_map"), dict) else {}
            y = pmap.get("yandex_market") if isinstance(pmap.get("yandex_market"), dict) else {}
            oz = pmap.get("ozon") if isinstance(pmap.get("ozon"), dict) else {}
            yid = str(y.get("id") or "").strip()
            yn = str(y.get("name") or "").strip()
            ozid = str(oz.get("id") or "").strip()
            ozn = str(oz.get("name") or "").strip()
            cname = str(r.get("catalog_name") or "").strip()
            if not cname:
                continue
            if not (yid or yn or ozid or ozn):
                continue
            out.append(
                {
                    "catalog_name": cname,
                    "group": _normalize_param_group(r.get("group"), cname, yn or ozn),
                    "yandex_id": yid,
                    "yandex_name": yn,
                    "yandex_kind": str(y.get("kind") or "").strip(),
                    "ozon_id": ozid,
                    "ozon_name": ozn,
                    "ozon_kind": str(oz.get("kind") or "").strip(),
                    "confirmed": bool(r.get("confirmed") or False),
                }
            )
    out.sort(
        key=lambda x: (
            0 if bool(x.get("confirmed")) else 1,
            str(x.get("catalog_name") or "").lower(),
            str(x.get("yandex_name") or x.get("ozon_name") or "").lower(),
        )
    )
    return out[: max(0, int(limit))]


def _template_pick_for_pair(
    y: Optional[Dict[str, Any]],
    templates: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    yid = str((y or {}).get("id") or "").strip()
    yn = _norm_name(str((y or {}).get("name") or ""))
    y_tokens = _tokens(str((y or {}).get("name") or ""))
    y_kind = _kind_group(str((y or {}).get("kind") or ""))

    def score(t: Dict[str, Any]) -> int:
        t_name = _norm_name(str(t.get("yandex_name") or ""))
        t_tokens = _tokens(str(t.get("yandex_name") or ""))
        t_kind = _kind_group(str(t.get("yandex_kind") or ""))
        s = 0
        if yid and yid == str(t.get("yandex_id") or "").strip():
            s += 9
        if yn and yn == t_name:
            s += 7
        elif yn and t_name and (yn in t_name or t_name in yn):
            s += 4
        if y_tokens and t_tokens:
            inter = len(y_tokens & t_tokens)
            union = max(1, len(y_tokens | t_tokens))
            j = inter / union
            if j >= 0.75:
                s += 4
            elif j >= 0.5:
                s += 3
            elif j >= 0.25:
                s += 1
        if y_kind and t_kind and y_kind == t_kind:
            s += 1
        if bool(t.get("confirmed")):
            s += 2
        return s

    best: Optional[Dict[str, Any]] = None
    best_score = 0
    for t in templates or []:
        sc = score(t)
        if sc > best_score:
            best_score = sc
            best = t
    if best_score >= 4:
        return best
    return None


def _deterministic_ai_rows(
    yandex_params: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
    feedback_doc: Optional[Dict[str, Any]] = None,
    template_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    by_name: Dict[str, Dict[str, Any]] = {}
    out: List[Dict[str, Any]] = []
    service = _service_names()

    def upsert_row(row: Dict[str, Any]) -> None:
        n = _norm_name(str(row.get("catalog_name") or ""))
        if not n:
            return
        cur = by_name.get(n)
        if not cur:
            by_name[n] = row
            out.append(row)
            return
        for p in MAPPING_PROVIDERS:
            dst = cur.get("provider_map", {}).get(p, {})
            src = row.get("provider_map", {}).get(p, {})
            if not dst.get("id") and src.get("id"):
                cur["provider_map"][p] = src
        cur["confirmed"] = bool(cur.get("confirmed") or row.get("confirmed"))

    for nm in service:
        upsert_row(_build_row(nm, None, confirmed=False))

    for er in _normalize_attr_rows(existing_rows):
        upsert_row(er)

    y_used: set[str] = set()
    yz = [x for x in yandex_params if isinstance(x, dict)]

    for y in yz:
        yid = str(y.get("id") or "").strip()
        if not yid or yid in y_used:
            continue
        t = _template_pick_for_pair(y, template_rows or [])
        name = str((t or {}).get("catalog_name") or "").strip() or str(y.get("name") or yid)
        grp = str((t or {}).get("group") or "").strip() or None
        upsert_row(_build_row(name, y, confirmed=bool((t or {}).get("confirmed")), group=grp))

    return _normalize_attr_rows(out)


async def _ollama_suggest_rows(
    category_name: str,
    yandex_params: List[Dict[str, Any]],
    existing_rows: List[Dict[str, Any]],
    feedback_doc: Optional[Dict[str, Any]] = None,
    template_rows: Optional[List[Dict[str, Any]]] = None,
) -> Optional[List[Dict[str, Any]]]:
    base_url = str(os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
    model = str(os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")).strip() or "qwen2.5:14b-instruct"

    sys_prompt = (
        "Ты эксперт по PIM и маркетплейсам. "
        "Нужно сопоставить характеристики категории для Я.Маркет. "
        "Сопоставляй только параметры с одинаковым смыслом. "
        "Ответ строго в JSON без markdown."
    )
    user_payload = {
        "category": category_name,
        "yandex_params": [
            {"id": str(x.get("id") or ""), "name": str(x.get("name") or ""), "kind": str(x.get("kind") or "")}
            for x in (yandex_params or [])
        ],
        "existing_rows": [
            {
                "catalog_name": str(r.get("catalog_name") or ""),
                "group": str(r.get("group") or ""),
            }
            for r in _normalize_attr_rows(existing_rows)
        ],
        "template_rows_from_saved_categories": [
            {
                "catalog_name": str(t.get("catalog_name") or ""),
                "group": str(t.get("group") or ""),
                "yandex_name": str(t.get("yandex_name") or ""),
                "confirmed": bool(t.get("confirmed") or False),
            }
            for t in (template_rows or [])[:180]
        ],
        "response_schema": {
            "rows": [
                {
                    "catalog_name": "string",
                    "group": "Артикулы|Описание|Медиа|О товаре|Логистика|Гарантия|Прочее",
                    "yandex_id": "string|null",
                    "confirmed": "boolean",
                }
            ]
        },
    }

    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0.1, "top_p": 0.9},
        "prompt": f"{sys_prompt}\n\nДанные:\n{json.dumps(user_payload, ensure_ascii=False)}",
    }

    timeout = httpx.Timeout(120.0, connect=5.0)
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
    if not isinstance(rows, list):
        return None

    y_map = {str(x.get("id") or "").strip(): x for x in (yandex_params or []) if str(x.get("id") or "").strip()}
    out: List[Dict[str, Any]] = []
    for rr in rows:
        if not isinstance(rr, dict):
            continue
        name = str(rr.get("catalog_name") or "").strip()
        if not name:
            continue
        group = str(rr.get("group") or "").strip()
        yid = str(rr.get("yandex_id") or "").strip()
        y = y_map.get(yid) if yid else None
        out.append(_build_row(name, y, confirmed=bool(rr.get("confirmed") or False), group=group))
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

    if provider_category_id and provider_category_id not in {x.get("id") for x in provider_items}:
        raise HTTPException(status_code=404, detail="PROVIDER_CATEGORY_NOT_FOUND")

    lock = with_lock("marketplace_category_mapping")
    lock.acquire()
    try:
        items = _load_mappings()
        row = items.get(catalog_id, {})
        if not isinstance(row, dict):
            row = {}

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
    cached_payload = _attr_categories_cache.get("payload")
    cached_ts = float(_attr_categories_cache.get("ts") or 0.0)
    if cached_payload and now - cached_ts < _ATTR_CATEGORIES_CACHE_TTL_SECONDS:
        return cached_payload

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
    _attr_categories_cache["ts"] = now
    _attr_categories_cache["payload"] = payload
    return payload


@router.get("/import/attributes/{catalog_category_id}")
def mapping_attribute_details(catalog_category_id: str) -> Dict[str, Any]:
    _migrate_mapping_documents_to_canonical_names()
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")

    cached = _attr_details_cache.get(cid)
    if cached and time.monotonic() - cached[0] < _ATTR_DETAILS_CACHE_TTL_SECONDS:
        return cached[1]

    catalog_nodes = _load_catalog_nodes()
    catalog_items = _catalog_rows(catalog_nodes)
    parent_by_id = _catalog_parent_map(catalog_nodes)
    cat = next((x for x in catalog_items if str(x.get("id")) == cid), None)
    if not cat:
        raise HTTPException(status_code=404, detail="CATALOG_CATEGORY_NOT_FOUND")

    mappings = _load_mappings()
    cat_mapping = _effective_mapping_for_catalog(cid, mappings, parent_by_id)
    if not cat_mapping:
        raise HTTPException(status_code=400, detail="CATEGORY_NOT_MAPPED")

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
    rows = _normalize_attr_rows(saved.get("rows") if isinstance(saved, dict) else [])
    template_rows = _collect_template_rows_from_saved(doc, exclude_category_id=cid, limit=320)
    suggested_rows = _deterministic_ai_rows(
        yandex_params,
        rows,
        feedback_doc=None,
        template_rows=template_rows,
    ) if yandex_params else []
    templates_db = load_templates_db()
    cat_to_tpls = templates_db.get("category_to_templates") if isinstance(templates_db.get("category_to_templates"), dict) else {}
    template_id = ""
    if isinstance(cat_to_tpls, dict):
        tids = cat_to_tpls.get(cid) if isinstance(cat_to_tpls.get(cid), list) else []
        template_id = str((tids or [""])[0] or "").strip()
    template = ((templates_db.get("templates") or {}).get(template_id) if template_id else None) or {}
    template_meta = template.get("meta") if isinstance(template, dict) and isinstance(template.get("meta"), dict) else {}

    payload = {
        "ok": True,
        "category": {"id": cid, "name": cat.get("name"), "path": cat.get("path")},
        "mapping": cat_mapping,
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
        "suggested_rows": suggested_rows,
        "suggested_rows_count": len(suggested_rows),
        "updated_at": saved.get("updated_at") if isinstance(saved, dict) else None,
        "template_id": template_id or None,
        "master_template": template_meta.get("master_template") if isinstance(template_meta.get("master_template"), dict) else None,
        "sources": template_meta.get("sources") if isinstance(template_meta.get("sources"), dict) else {},
    }
    _attr_details_cache[cid] = (time.monotonic(), payload)
    return payload


@router.put("/import/attributes/{catalog_category_id}")
def mapping_attribute_save(catalog_category_id: str, req: SaveAttrMappingReq) -> Dict[str, Any]:
    _migrate_mapping_documents_to_canonical_names()
    cid = str(catalog_category_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="CATALOG_CATEGORY_REQUIRED")
    _attr_categories_cache["ts"] = 0.0
    _attr_categories_cache["payload"] = None
    _attr_details_cache.pop(cid, None)

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
        write_doc(ATTR_MAPPING_PATH, doc)
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
        raise HTTPException(status_code=400, detail="CATEGORY_NOT_MAPPED")

    yandex_cat_id = str(cat_mapping.get("yandex_market") or "").strip()
    yandex_params = _load_yandex_params(yandex_cat_id)

    doc = _load_attr_mapping_doc()
    items = doc.get("items") if isinstance(doc.get("items"), dict) else {}
    if not isinstance(items, dict):
        items = {}
    saved = items.get(cid) if isinstance(items.get(cid), dict) else {}
    existing_rows = _normalize_attr_rows(saved.get("rows") if isinstance(saved, dict) else [])
    feedback_doc = _load_attr_feedback_doc()
    template_rows = _collect_template_rows_from_saved(doc, exclude_category_id=cid, limit=280)

    rows_ai: Optional[List[Dict[str, Any]]] = None
    engine = "fallback"
    try:
        rows_ai = await _ollama_suggest_rows(
            category_name=str(cat.get("path") or cat.get("name") or cid),
            yandex_params=yandex_params,
            existing_rows=existing_rows,
            feedback_doc=feedback_doc,
            template_rows=template_rows,
        )
        if rows_ai:
            engine = "ollama"
    except Exception:
        rows_ai = None

    rows_final = rows_ai or _deterministic_ai_rows(
        yandex_params,
        existing_rows,
        feedback_doc=feedback_doc,
        template_rows=template_rows,
    )
    rows_final = _apply_group_locks(rows_final)

    if req.apply:
        lock = with_lock("marketplace_attribute_mapping")
        lock.acquire()
        try:
            doc_apply = _load_attr_mapping_doc()
            doc_items = doc_apply.get("items") if isinstance(doc_apply.get("items"), dict) else {}
            if not isinstance(doc_items, dict):
                doc_items = {}
            doc_items[cid] = {"rows": rows_final, "updated_at": _now_iso()}
            doc_apply["items"] = doc_items
            write_doc(ATTR_MAPPING_PATH, doc_apply)
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
    }
