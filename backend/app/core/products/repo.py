# backend/app/core/products/repo.py
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..json_store import DATA_DIR, read_doc, write_doc, with_lock, JsonStoreError
from app.storage.json_store import (
    load_dictionaries_db,
    save_dictionaries_db,
    load_products_db,
    save_products_db,
    new_id,
)

PRODUCTS_PATH = DATA_DIR / "products.json"
GT_INDEX_PATH = DATA_DIR / "sku_gt_index.json"
# ✅ NEW: PIM SKU index (digits-only)
PIM_INDEX_PATH = DATA_DIR / "sku_pim_index.json"

CAT_INDEX_PATH = DATA_DIR / "product_category_index.json"
COUNTERS_PATH = DATA_DIR / "counters.json"

# ✅ синхронизация с catalog.py (JSON-товары каталога)
CATALOG_PRODUCTS_PATH = DATA_DIR / "catalog_products.json"

# gt/id: разрешаем A-Za-z0-9_- как раньше
SKU_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# pim: только цифры, разумный лимит
SKU_PIM_RE = re.compile(r"^[0-9]{1,32}$")

SERVICE_DICT_META: Dict[str, Dict[str, str]] = {
    "sku_pim": {"title": "SKU PIM", "type": "number", "scope": "variant"},
    "sku_gt": {"title": "SKU GT", "type": "number", "scope": "variant"},
    "title": {"title": "Наименование товара", "type": "text", "scope": "feature"},
    "barcode": {"title": "Штрихкод", "type": "number", "scope": "both"},
}


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
    for v in values:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(v)
    return dedup


def _build_service_value_counters(products: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    counters: Dict[str, Dict[str, int]] = {k: {} for k in SERVICE_DICT_META.keys()}
    for p in products:
        sku_pim = str(p.get("sku_pim") or "").strip()
        sku_gt = str(p.get("sku_gt") or "").strip()
        if sku_pim:
            counters["sku_pim"][sku_pim] = int(counters["sku_pim"].get(sku_pim, 0)) + 1
        if sku_gt:
            counters["sku_gt"][sku_gt] = int(counters["sku_gt"].get(sku_gt, 0)) + 1
        title = str(p.get("title") or "").strip()
        if title:
            counters["title"][title] = int(counters["title"].get(title, 0)) + 1
        for bc in _extract_barcodes_from_product(p):
            counters["barcode"][bc] = int(counters["barcode"].get(bc, 0)) + 1
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
    for v in values:
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _build_feature_dict_counters(
    products: List[Dict[str, Any]],
    dict_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    counters_by_dict_id: Dict[str, Dict[str, int]] = {}
    for p in products:
        content = p.get("content") if isinstance(p.get("content"), dict) else {}
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
            did = str(target_dict.get("id") or "").strip()
            if not did:
                continue
            bucket = counters_by_dict_id.setdefault(did, {})
            for v in values:
                bucket[v] = int(bucket.get(v, 0)) + 1
    return counters_by_dict_id


def _find_service_dict(items: List[Dict[str, Any]], field_code: str) -> Optional[Dict[str, Any]]:
    field_code_norm = _normalize_lookup(field_code)
    aliases: Dict[str, set[str]] = {
        "sku_pim": {"sku_pim", "sku_pim", "sku_pim"},
        "sku_gt": {"sku_gt", "sku_gt"},
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
        d = _ensure_service_dict(items, field_code, now)
        meta = d.get("meta") if isinstance(d.get("meta"), dict) else {}
        meta["service"] = True
        meta["required"] = True
        d["meta"] = meta
        next_items = _service_dict_items_from_counter(service_counters.get(field_code, {}), now)
        d["items"] = next_items
        if not str(d.get("code") or "").strip():
            d["code"] = field_code
        if not str(d.get("dict_id") or "").strip():
            d["dict_id"] = str(d.get("id") or f"dict_{field_code}")
        d["updated_at"] = now
        if not str(d.get("created_at") or "").strip():
            d["created_at"] = now

    service_dict_ids = {str(_ensure_service_dict(items, code, now).get("id") or "") for code in SERVICE_DICT_META.keys()}
    for d in items:
        if not isinstance(d, dict):
            continue
        did = str(d.get("id") or "").strip()
        if not did or did in service_dict_ids:
            continue
        counter = feature_counters_by_dict_id.get(did)
        if counter is None:
            continue
        d["items"] = _service_dict_items_from_counter(counter, now)
        d["updated_at"] = now
        if not str(d.get("created_at") or "").strip():
            d["created_at"] = now

    db["items"] = items
    save_dictionaries_db(db)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _default_content() -> Dict[str, Any]:
    return {
        "description": "",
        "media": [],  # legacy: mirrors media_images
        "media_images": [],
        "media_videos": [],
        "media_cover": [],
        "documents": [],
        "links": [],
        "features": [],
        "analogs": [],
        "related": [],
    }

def _merge_content(current: Any, patch: Any) -> Dict[str, Any]:
    base = current if isinstance(current, dict) else {}
    if not isinstance(patch, dict):
        return dict(base)
    out = dict(base)
    for k, v in patch.items():
        out[str(k)] = v
    return out

def _next_product_id() -> str:
    lock = with_lock("counters")
    lock.acquire()
    try:
        counters = read_doc(
            COUNTERS_PATH,
            default={
                "version": 1,
                "next_product_id": 1,
                "next_variant_id": 1,
                "next_sku_pim": 1,
                "next_sku_gt": 1,
            },
        )
        n = int(counters.get("next_product_id", 1))
        counters["next_product_id"] = n + 1
        write_doc(COUNTERS_PATH, counters)
        return f"product_{n}"
    finally:
        lock.release()


def allocate_sku_pairs(count: int) -> List[Dict[str, str]]:
    """
    Резервирует N пар (PIM/GT).
    """
    if count <= 0:
        return []
    lock = with_lock("counters")
    lock.acquire()
    try:
        counters = read_doc(
            COUNTERS_PATH,
            default={
                "version": 1,
                "next_product_id": 1,
                "next_variant_id": 1,
                "next_sku_pim": 1,
                "next_sku_gt": 1,
            },
        )
        pim = int(counters.get("next_sku_pim", 1))
        gt = int(counters.get("next_sku_gt", 1))

        out: List[Dict[str, str]] = []
        for i in range(count):
            out.append(
                {
                    "sku_pim": str(pim + i),
                    "sku_gt": str(gt + i),
                }
            )

        counters["next_sku_pim"] = pim + count
        counters["next_sku_gt"] = gt + count
        write_doc(COUNTERS_PATH, counters)
        return out
    finally:
        lock.release()


def load_products() -> Dict[str, Any]:
    return load_products_db()


def save_products(doc: Dict[str, Any]) -> None:
    save_products_db(doc)


def _build_indexes(products_doc: Dict[str, Any]) -> tuple[Dict[str, str], Dict[str, str], Dict[str, List[str]]]:
    items = products_doc.get("items") if isinstance(products_doc.get("items"), list) else []
    gt_map: Dict[str, str] = {}
    pim_map: Dict[str, str] = {}
    cat_map: Dict[str, List[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or "").strip()
        if not pid:
            continue
        sku_gt = _norm_sku(item.get("sku_gt"))
        sku_pim = _norm_sku(item.get("sku_pim"))
        category_id = str(item.get("category_id") or "").strip()
        if sku_gt and sku_gt not in gt_map:
            gt_map[sku_gt] = pid
        if sku_pim and sku_pim not in pim_map:
            pim_map[sku_pim] = pid
        if category_id:
            cat_map.setdefault(category_id, [])
            cat_map[category_id].append(pid)
    return gt_map, pim_map, cat_map


def load_gt_index() -> Dict[str, Any]:
    gt_map, _, _ = _build_indexes(load_products())
    return {"version": 1, "gt_to_product_id": gt_map}


def save_gt_index(doc: Dict[str, Any]) -> None:
    write_doc(GT_INDEX_PATH, doc)


def load_pim_index() -> Dict[str, Any]:
    _, pim_map, _ = _build_indexes(load_products())
    return {"version": 1, "pim_to_product_id": pim_map}


def save_pim_index(doc: Dict[str, Any]) -> None:
    write_doc(PIM_INDEX_PATH, doc)


def load_category_index() -> Dict[str, Any]:
    _, _, cat_map = _build_indexes(load_products())
    return {"version": 1, "category_to_product_ids": cat_map}


def save_category_index(doc: Dict[str, Any]) -> None:
    write_doc(CAT_INDEX_PATH, doc)


# =========================
# ✅ catalog_products.json helpers
# =========================
def _load_catalog_products() -> List[Dict[str, Any]]:
    # catalog.py ожидает список [{id,name,category_id}, ...]
    doc = load_products()
    items = doc.get("items") if isinstance(doc.get("items"), list) else []
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "id": str(item.get("id") or "").strip(),
                "name": str(item.get("title") or item.get("name") or "").strip(),
                "category_id": str(item.get("category_id") or "").strip(),
            }
        )
    return out


def _save_catalog_products(items: List[Dict[str, Any]]) -> None:
    write_doc(CATALOG_PRODUCTS_PATH, items)


def _upsert_catalog_product(product_id: str, title: str, category_id: str) -> None:
    """
    Синхронизация с catalog.py:
      - id = product_{n} (тот же id)
      - name = title
      - category_id = category_id
    """
    pid = str(product_id)
    name = (title or "").strip()
    cid = (category_id or "").strip()

    if not pid or not cid:
        return

    items = _load_catalog_products()

    found = False
    for it in items:
        if str(it.get("id")) == pid:
            it["name"] = name
            it["category_id"] = cid
            found = True
            break

    if not found:
        items.append({"id": pid, "name": name, "category_id": cid})

    _save_catalog_products(items)


def _remove_catalog_products_by_ids(product_ids: List[str]) -> None:
    if not product_ids:
        return
    remove_set = {str(x).strip() for x in product_ids if str(x).strip()}
    if not remove_set:
        return
    items = _load_catalog_products()
    next_items = [it for it in items if str(it.get("id") or "").strip() not in remove_set]
    if len(next_items) != len(items):
        _save_catalog_products(next_items)


# =========================
# SKU helpers
# =========================
def _norm_sku(s: Optional[str]) -> str:
    return (s or "").strip()


def _validate_sku(field: str, sku: str) -> None:
    if not sku:
        return
    if not SKU_RE.match(sku):
        raise JsonStoreError(f"BAD_{field.upper()}")


def _validate_sku_pim(sku_pim: str) -> None:
    if not sku_pim:
        return
    if not SKU_PIM_RE.match(sku_pim):
        raise JsonStoreError("BAD_SKU_PIM")


# =========================
# Category index helpers
# =========================
def _remove_from_category_index(cat_idx: Dict[str, Any], category_id: str, product_id: str) -> None:
    m = cat_idx.get("category_to_product_ids", {}) or {}
    arr = m.get(category_id) or []
    if isinstance(arr, list) and product_id in arr:
        arr = [x for x in arr if x != product_id]
        m[category_id] = arr
    cat_idx["category_to_product_ids"] = m


def _add_to_category_index(cat_idx: Dict[str, Any], category_id: str, product_id: str) -> None:
    m = cat_idx.get("category_to_product_ids", {}) or {}
    arr = m.get(category_id)
    if not isinstance(arr, list):
        arr = []
    if product_id not in arr:
        arr.append(product_id)
    m[category_id] = arr
    cat_idx["category_to_product_ids"] = m


# =========================
# CRUD
# =========================
def create_product(payload: Dict[str, Any]) -> Dict[str, Any]:
    lock = with_lock("products_write")
    lock.acquire()
    try:
        products_doc = load_products()
        gt_doc = load_gt_index()
        pim_doc = load_pim_index()
        cat_doc = load_category_index()

        items: List[Dict[str, Any]] = products_doc.get("items", []) or []
        gt_map: Dict[str, str] = gt_doc.get("gt_to_product_id", {}) or {}
        pim_map: Dict[str, str] = pim_doc.get("pim_to_product_id", {}) or {}

        category_id = (payload.get("category_id") or "").strip()
        if not category_id:
            raise JsonStoreError("CATEGORY_REQUIRED")

        title = (payload.get("title") or "").strip()
        if not title:
            raise JsonStoreError("TITLE_REQUIRED")

        group_id = (payload.get("group_id") or "").strip()
        ptype = "multi" if group_id else (payload.get("type") or "single").strip()
        if ptype not in ("single", "multi"):
            raise JsonStoreError("BAD_TYPE")

        # ✅ PIM SKU: принимаем sku_pim ИЛИ sku (backward compatible)
        sku_pim = _norm_sku(payload.get("sku_pim") or payload.get("sku"))
        _validate_sku_pim(sku_pim)
        if sku_pim and sku_pim in pim_map:
            raise JsonStoreError("DUPLICATE_SKU_PIM")

        sku_gt = _norm_sku(payload.get("sku_gt"))

        _validate_sku("sku_gt", sku_gt)

        if sku_gt and sku_gt in gt_map:
            raise JsonStoreError("DUPLICATE_SKU_GT")

        selected_params = payload.get("selected_params") or []
        if not isinstance(selected_params, list):
            selected_params = []
        selected_params = [str(x).strip() for x in selected_params if str(x).strip()]

        feature_params = payload.get("feature_params") or []
        if not isinstance(feature_params, list):
            feature_params = []
        feature_params = [str(x).strip() for x in feature_params if str(x).strip()]

        exports_enabled = payload.get("exports_enabled") or {}
        if not isinstance(exports_enabled, dict):
            exports_enabled = {}

        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, dict):
            content = _default_content()

        pid = _next_product_id()
        now = _now_iso()

        obj = {
            "id": pid,
            "category_id": category_id,
            "type": ptype,              # single|multi
            "status": "draft",          # draft|active|archived
            "title": title,

            # ✅ 2 SKU:
            "sku_pim": sku_pim,         # digits-only
            "sku_gt": sku_gt,           # GT

            "selected_params": selected_params,
            "feature_params": feature_params,
            "exports_enabled": exports_enabled,
            "created_at": now,
            "updated_at": now,
            "content": content,
        }
        if group_id:
            obj["group_id"] = group_id

        items.append(obj)
        products_doc["items"] = items

        # indexes
        if sku_pim:
            pim_map[sku_pim] = pid
        if sku_gt:
            gt_map[sku_gt] = pid

        pim_doc["pim_to_product_id"] = pim_map
        gt_doc["gt_to_product_id"] = gt_map

        _add_to_category_index(cat_doc, category_id, pid)

        save_products(products_doc)
        save_pim_index(pim_doc)
        save_gt_index(gt_doc)
        save_category_index(cat_doc)

        # ✅ синхронизируем с catalog.py (catalog_products.json)
        _upsert_catalog_product(pid, title, category_id)
        sync_service_dictionaries_from_products(items)

        return obj
    finally:
        lock.release()


def get_product(product_id: str) -> Dict[str, Any]:
    doc = load_products()
    items = doc.get("items", []) or []
    p = next((x for x in items if x.get("id") == product_id), None)
    if not p:
        raise JsonStoreError("PRODUCT_NOT_FOUND")
    return p


def update_product(product_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    lock = with_lock("products_write")
    lock.acquire()
    try:
        products_doc = load_products()
        gt_doc = load_gt_index()
        pim_doc = load_pim_index()
        cat_doc = load_category_index()

        items: List[Dict[str, Any]] = products_doc.get("items", []) or []
        gt_map: Dict[str, str] = gt_doc.get("gt_to_product_id", {}) or {}
        pim_map: Dict[str, str] = pim_doc.get("pim_to_product_id", {}) or {}

        p = next((x for x in items if x.get("id") == product_id), None)
        if not p:
            raise JsonStoreError("PRODUCT_NOT_FOUND")

        old_pim = _norm_sku(p.get("sku_pim"))
        old_gt = _norm_sku(p.get("sku_gt"))
        old_cat = (p.get("category_id") or "").strip()

        if "title" in patch:
            title = (patch.get("title") or "").strip()
            if not title:
                raise JsonStoreError("TITLE_REQUIRED")
            p["title"] = title

        if "type" in patch:
            ptype = (patch.get("type") or "single").strip()
            if ptype not in ("single", "multi"):
                raise JsonStoreError("BAD_TYPE")
            p["type"] = ptype

        if "status" in patch:
            st = (patch.get("status") or "").strip()
            if st not in ("draft", "active", "archived"):
                raise JsonStoreError("BAD_STATUS")
            p["status"] = st

        if "group_id" in patch:
            gid = (patch.get("group_id") or "").strip()
            if gid:
                p["group_id"] = gid
                p["type"] = "multi"
            else:
                p.pop("group_id", None)
                p["type"] = "single"

        if "category_id" in patch:
            new_cat = (patch.get("category_id") or "").strip()
            if not new_cat:
                raise JsonStoreError("CATEGORY_REQUIRED")
            p["category_id"] = new_cat

        if "selected_params" in patch:
            sp = patch.get("selected_params") or []
            if not isinstance(sp, list):
                sp = []
            p["selected_params"] = [str(x).strip() for x in sp if str(x).strip()]

        if "feature_params" in patch:
            fp = patch.get("feature_params") or []
            if not isinstance(fp, list):
                fp = []
            p["feature_params"] = [str(x).strip() for x in fp if str(x).strip()]

        if "exports_enabled" in patch:
            ee = patch.get("exports_enabled") or {}
            if not isinstance(ee, dict):
                ee = {}
            p["exports_enabled"] = ee

        if "content" in patch:
            p["content"] = _merge_content(p.get("content"), patch.get("content"))

        # ✅ sku_pim (digits-only). также поддержим patch["sku"] как алиас
        if "sku_pim" in patch or "sku" in patch:
            new_pim = _norm_sku(patch.get("sku_pim") if "sku_pim" in patch else patch.get("sku"))
            _validate_sku_pim(new_pim)
            if new_pim and pim_map.get(new_pim) not in (None, product_id):
                raise JsonStoreError("DUPLICATE_SKU_PIM")
            p["sku_pim"] = new_pim

        if "sku_gt" in patch:
            new_gt = _norm_sku(patch.get("sku_gt"))
            _validate_sku("sku_gt", new_gt)
            if new_gt and gt_map.get(new_gt) not in (None, product_id):
                raise JsonStoreError("DUPLICATE_SKU_GT")
            p["sku_gt"] = new_gt

        # reindex pim
        new_pim_final = _norm_sku(p.get("sku_pim"))
        if old_pim and pim_map.get(old_pim) == product_id and old_pim != new_pim_final:
            pim_map.pop(old_pim, None)
        if new_pim_final:
            pim_map[new_pim_final] = product_id

        # reindex gt
        new_gt_final = _norm_sku(p.get("sku_gt"))
        if old_gt and gt_map.get(old_gt) == product_id and old_gt != new_gt_final:
            gt_map.pop(old_gt, None)
        if new_gt_final:
            gt_map[new_gt_final] = product_id

        # category index
        new_cat_final = (p.get("category_id") or "").strip()
        if old_cat and old_cat != new_cat_final:
            _remove_from_category_index(cat_doc, old_cat, product_id)
            _add_to_category_index(cat_doc, new_cat_final, product_id)
        elif new_cat_final:
            _add_to_category_index(cat_doc, new_cat_final, product_id)

        p["updated_at"] = _now_iso()

        products_doc["items"] = items
        pim_doc["pim_to_product_id"] = pim_map
        gt_doc["gt_to_product_id"] = gt_map

        save_products(products_doc)
        save_pim_index(pim_doc)
        save_gt_index(gt_doc)
        save_category_index(cat_doc)

        # ✅ синхронизируем с catalog.py
        _upsert_catalog_product(
            product_id,
            str(p.get("title") or ""),
            str(p.get("category_id") or ""),
        )
        sync_service_dictionaries_from_products(items)

        return p
    finally:
        lock.release()


def list_products_by_category(category_id: str) -> List[Dict[str, Any]]:
    category_id = (category_id or "").strip()
    if not category_id:
        return []
    cat_doc = load_category_index()
    m = cat_doc.get("category_to_product_ids", {}) or {}
    ids = m.get(category_id) or []
    if not isinstance(ids, list) or not ids:
        return []
    prod_doc = load_products()
    items = prod_doc.get("items", []) or []
    set_ids = set(map(str, ids))
    out = [x for x in items if str(x.get("id")) in set_ids]
    out.sort(key=lambda x: (x.get("created_at") or ""), reverse=True)
    return out


def find_product_by_sku(
    sku_pim: Optional[str] = None,
    sku_gt: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    sku_pim = _norm_sku(sku_pim)
    sku_gt = _norm_sku(sku_gt)

    if not sku_pim and not sku_gt:
        return None

    if sku_pim:
        pim_doc = load_pim_index()
        pid = (pim_doc.get("pim_to_product_id", {}) or {}).get(sku_pim)
        if pid:
            try:
                return get_product(pid)
            except JsonStoreError:
                return None

    if sku_gt:
        gt_doc = load_gt_index()
        pid = (gt_doc.get("gt_to_product_id", {}) or {}).get(sku_gt)
        if pid:
            try:
                return get_product(pid)
            except JsonStoreError:
                return None

    return None


def delete_products_bulk(product_ids: List[str]) -> int:
    delete_ids = {str(x).strip() for x in (product_ids or []) if str(x).strip()}
    if not delete_ids:
        return 0

    lock = with_lock("products_write")
    lock.acquire()
    try:
        products_doc = load_products()
        items: List[Dict[str, Any]] = products_doc.get("items", []) or []
        prev_len = len(items)
        next_items = [p for p in items if str(p.get("id") or "").strip() not in delete_ids]
        deleted = prev_len - len(next_items)
        if deleted <= 0:
            return 0

        gt_map: Dict[str, str] = {}
        pim_map: Dict[str, str] = {}
        cat_map: Dict[str, List[str]] = {}

        for p in next_items:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            sku_pim = _norm_sku(p.get("sku_pim"))
            sku_gt = _norm_sku(p.get("sku_gt"))
            cat = str(p.get("category_id") or "").strip()
            if sku_pim and sku_pim not in pim_map:
                pim_map[sku_pim] = pid
            if sku_gt and sku_gt not in gt_map:
                gt_map[sku_gt] = pid
            if cat:
                cat_map.setdefault(cat, [])
                cat_map[cat].append(pid)

        products_doc["items"] = next_items
        save_products(products_doc)
        save_pim_index({"version": 1, "pim_to_product_id": pim_map})
        save_gt_index({"version": 1, "gt_to_product_id": gt_map})
        save_category_index({"version": 1, "category_to_product_ids": cat_map})
        _remove_catalog_products_by_ids(list(delete_ids))
        sync_service_dictionaries_from_products(next_items)
        return deleted
    finally:
        lock.release()
