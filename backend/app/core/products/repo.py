from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.json_store import JsonStoreError
from app.core.products.service import (
    allocate_sku_pairs_service,
    create_product_service,
    delete_products_bulk_service,
    get_product_service,
    list_products_by_category_service,
    patch_product_service,
)
from app.storage.json_store import load_dictionaries_db, save_dictionaries_db, new_id
from app.storage.relational_pim_store import query_products_full

SKU_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SKU_PIM_RE = re.compile(r"^[0-9]{1,32}$")

SERVICE_DICT_META: Dict[str, Dict[str, str]] = {
    "sku_pim": {"title": "SKU PIM", "type": "number", "scope": "variant"},
    "sku_gt": {"title": "SKU GT", "type": "number", "scope": "variant"},
    "title": {"title": "Наименование товара", "type": "text", "scope": "feature"},
    "barcode": {"title": "Штрихкод", "type": "number", "scope": "both"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_sku(value: Optional[str]) -> str:
    return str(value or "").strip()


def _validate_sku(field: str, sku: str) -> None:
    if sku and not SKU_RE.match(sku):
        raise JsonStoreError(f"BAD_{field.upper()}")


def _validate_sku_pim(sku_pim: str) -> None:
    if sku_pim and not SKU_PIM_RE.match(sku_pim):
        raise JsonStoreError("BAD_SKU_PIM")


def _normalize_lookup(s: Any) -> str:
    v = str(s or "").strip().lower()
    if not v:
        return ""
    v = v.replace("-", "_").replace(" ", "_")
    return "_".join(part for part in v.split("_") if part)


def _extract_scalar_values(raw: Any) -> List[str]:
    out: List[str] = []
    if raw is None:
        return out
    if isinstance(raw, (list, tuple, set)):
        for it in raw:
            out.extend(_extract_scalar_values(it))
        return out
    if isinstance(raw, dict):
        for key in ("value", "values", "id", "name", "title"):
            if key in raw:
                out.extend(_extract_scalar_values(raw.get(key)))
        return out
    s = str(raw).strip()
    if s:
        out.append(s)
    return out


def _extract_barcodes_from_product(product: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    for key in ("barcode", "bar_code", "ean", "gtin"):
        values.extend(_extract_scalar_values(product.get(key)))

    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        code = _normalize_lookup(feature.get("code"))
        name = _normalize_lookup(feature.get("name"))
        if code in {"barcode", "штрихкод", "ean", "gtin"} or name in {"barcode", "штрихкод"}:
            values.extend(_extract_scalar_values(feature.get("value")))
            values.extend(_extract_scalar_values(feature.get("values")))

    dedup: List[str] = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(value)
    return dedup


def _build_service_value_counters(products: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    counters: Dict[str, Dict[str, int]] = {k: {} for k in SERVICE_DICT_META.keys()}
    for product in products:
        sku_pim = str(product.get("sku_pim") or "").strip()
        sku_gt = str(product.get("sku_gt") or "").strip()
        if sku_pim:
            counters["sku_pim"][sku_pim] = int(counters["sku_pim"].get(sku_pim, 0)) + 1
        if sku_gt:
            counters["sku_gt"][sku_gt] = int(counters["sku_gt"].get(sku_gt, 0)) + 1
        title = str(product.get("title") or "").strip()
        if title:
            counters["title"][title] = int(counters["title"].get(title, 0)) + 1
        for barcode in _extract_barcodes_from_product(product):
            counters["barcode"][barcode] = int(counters["barcode"].get(barcode, 0)) + 1
    return counters


def _build_dict_index(items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        candidates = {
            _normalize_lookup(item.get("code")),
            _normalize_lookup(item.get("title")),
            _normalize_lookup(str(item.get("id") or "").removeprefix("dict_")),
            _normalize_lookup(item.get("dict_id")),
        }
        for key in candidates:
            if key and key not in index:
                index[key] = item
    return index


def _dict_key_candidates_from_feature(feature: Dict[str, Any]) -> List[str]:
    keys: List[str] = []
    for raw in (
        feature.get("dict_id"),
        feature.get("code"),
        feature.get("name"),
        feature.get("title"),
        feature.get("parameter"),
    ):
        norm = _normalize_lookup(raw)
        if norm and norm not in keys:
            keys.append(norm)
    return keys


def _feature_values(feature: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    values.extend(_extract_scalar_values(feature.get("value")))
    values.extend(_extract_scalar_values(feature.get("values")))
    out: List[str] = []
    seen = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _build_feature_dict_counters(
    products: List[Dict[str, Any]],
    dict_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    counters_by_dict_id: Dict[str, Dict[str, int]] = {}
    for product in products:
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        features = content.get("features") if isinstance(content.get("features"), list) else []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            values = _feature_values(feature)
            if not values:
                continue
            target_dict: Optional[Dict[str, Any]] = None
            for key in _dict_key_candidates_from_feature(feature):
                if key in dict_index:
                    target_dict = dict_index[key]
                    break
            if not target_dict:
                continue
            dict_id = str(target_dict.get("id") or "").strip()
            if not dict_id:
                continue
            bucket = counters_by_dict_id.setdefault(dict_id, {})
            for value in values:
                bucket[value] = int(bucket.get(value, 0)) + 1
    return counters_by_dict_id


def _find_service_dict(items: List[Dict[str, Any]], field_code: str) -> Optional[Dict[str, Any]]:
    field_code_norm = _normalize_lookup(field_code)
    aliases: Dict[str, set[str]] = {
        "sku_pim": {"sku_pim"},
        "sku_gt": {"sku_gt"},
        "title": {"title", "naimenovanie_tovara", "наименование_товара"},
        "barcode": {"barcode", "штрихкод"},
    }
    expected = aliases.get(field_code_norm, {field_code_norm})

    for item in items:
        if not isinstance(item, dict):
            continue
        code_norm = _normalize_lookup(item.get("code"))
        title_norm = _normalize_lookup(item.get("title"))
        dict_id_norm = _normalize_lookup(str(item.get("id") or "").removeprefix("dict_"))
        if code_norm in expected or title_norm in expected or dict_id_norm in expected:
            return item
    return None


def _ensure_service_dict(items: List[Dict[str, Any]], field_code: str, now: str) -> Dict[str, Any]:
    existed = _find_service_dict(items, field_code)
    if existed:
        return existed
    meta = SERVICE_DICT_META[field_code]
    dict_id = f"dict_{field_code}"
    created = {
        "id": dict_id,
        "title": meta["title"],
        "code": field_code,
        "attr_id": f"attr_{field_code}_{new_id()[:6]}",
        "type": meta["type"],
        "scope": meta["scope"],
        "dict_id": dict_id,
        "items": [],
        "aliases": {},
        "meta": {"service": True, "required": True},
        "created_at": now,
        "updated_at": now,
    }
    items.append(created)
    return created


def _service_dict_items_from_counter(counter: Dict[str, int], now: str) -> List[Dict[str, Any]]:
    def sort_key(item: tuple[str, int]) -> tuple[int, str]:
        value = item[0]
        if value.isdigit():
            return (0, f"{int(value):020d}")
        return (1, value.lower())

    out: List[Dict[str, Any]] = []
    for value, count in sorted(counter.items(), key=sort_key):
        out.append(
            {
                "value": value,
                "count": int(count),
                "last_seen": now,
                "sources": {"products": int(count)},
            }
        )
    return out


def sync_service_dictionaries_from_products(products: List[Dict[str, Any]]) -> None:
    service_counters = _build_service_value_counters(products)
    db = load_dictionaries_db()
    items = db.get("items", [])
    if not isinstance(items, list):
        items = []
        db["items"] = items

    now = _now_iso()
    dict_index = _build_dict_index(items)
    feature_counters_by_dict_id = _build_feature_dict_counters(products, dict_index)

    for field_code in SERVICE_DICT_META.keys():
        dictionary = _ensure_service_dict(items, field_code, now)
        meta = dictionary.get("meta") if isinstance(dictionary.get("meta"), dict) else {}
        meta["service"] = True
        meta["required"] = True
        dictionary["meta"] = meta
        dictionary["items"] = _service_dict_items_from_counter(service_counters.get(field_code, {}), now)
        if not str(dictionary.get("code") or "").strip():
            dictionary["code"] = field_code
        if not str(dictionary.get("dict_id") or "").strip():
            dictionary["dict_id"] = str(dictionary.get("id") or f"dict_{field_code}")
        dictionary["updated_at"] = now
        if not str(dictionary.get("created_at") or "").strip():
            dictionary["created_at"] = now

    service_dict_ids = {
        str(_ensure_service_dict(items, code, now).get("id") or "")
        for code in SERVICE_DICT_META.keys()
    }
    for dictionary in items:
        if not isinstance(dictionary, dict):
            continue
        dict_id = str(dictionary.get("id") or "").strip()
        if not dict_id or dict_id in service_dict_ids:
            continue
        counter = feature_counters_by_dict_id.get(dict_id)
        if counter is None:
            continue
        dictionary["items"] = _service_dict_items_from_counter(counter, now)
        dictionary["updated_at"] = now
        if not str(dictionary.get("created_at") or "").strip():
            dictionary["created_at"] = now

    db["items"] = items
    save_dictionaries_db(db)


def load_products() -> Dict[str, Any]:
    return {"version": 1, "items": query_products_full()}


def save_products(doc: Dict[str, Any]) -> None:
    raise JsonStoreError("FULL_PRODUCTS_WRITE_DISABLED")


def _build_indexes(products_doc: Dict[str, Any]) -> tuple[Dict[str, str], Dict[str, str], Dict[str, List[str]]]:
    items = products_doc.get("items") if isinstance(products_doc.get("items"), list) else []
    gt_map: Dict[str, str] = {}
    pim_map: Dict[str, str] = {}
    cat_map: Dict[str, List[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("id") or "").strip()
        if not product_id:
            continue
        sku_gt = _norm_sku(item.get("sku_gt"))
        sku_pim = _norm_sku(item.get("sku_pim"))
        category_id = str(item.get("category_id") or "").strip()
        if sku_gt and sku_gt not in gt_map:
            gt_map[sku_gt] = product_id
        if sku_pim and sku_pim not in pim_map:
            pim_map[sku_pim] = product_id
        if category_id:
            cat_map.setdefault(category_id, [])
            cat_map[category_id].append(product_id)
    return gt_map, pim_map, cat_map


def load_gt_index() -> Dict[str, Any]:
    gt_map, _, _ = _build_indexes(load_products())
    return {"version": 1, "gt_to_product_id": gt_map}


def save_gt_index(doc: Dict[str, Any]) -> None:
    return None


def load_pim_index() -> Dict[str, Any]:
    _, pim_map, _ = _build_indexes(load_products())
    return {"version": 1, "pim_to_product_id": pim_map}


def save_pim_index(doc: Dict[str, Any]) -> None:
    return None


def load_category_index() -> Dict[str, Any]:
    _, _, cat_map = _build_indexes(load_products())
    return {"version": 1, "category_to_product_ids": cat_map}


def save_category_index(doc: Dict[str, Any]) -> None:
    return None


def allocate_sku_pairs(count: int) -> List[Dict[str, str]]:
    return list(allocate_sku_pairs_service(count).get("items") or [])


def create_product(payload: Dict[str, Any]) -> Dict[str, Any]:
    return create_product_service(payload)


def get_product(product_id: str) -> Dict[str, Any]:
    return dict(get_product_service(product_id, include_variants=False).get("product") or {})


def update_product(product_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    return dict(patch_product_service(product_id, patch).get("product") or {})


def list_products_by_category(category_id: str) -> List[Dict[str, Any]]:
    return list(list_products_by_category_service(category_id).get("items") or [])


def find_product_by_sku(
    sku_pim: Optional[str] = None,
    sku_gt: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    sku_pim = _norm_sku(sku_pim)
    sku_gt = _norm_sku(sku_gt)
    items = query_products_full()
    if sku_pim:
        for item in items:
            if _norm_sku(item.get("sku_pim")) == sku_pim:
                return item
    if sku_gt:
        for item in items:
            if _norm_sku(item.get("sku_gt")) == sku_gt:
                return item
    return None


def delete_products_bulk(product_ids: List[str]) -> int:
    return int(delete_products_bulk_service(product_ids).get("deleted") or 0)
