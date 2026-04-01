from __future__ import annotations

import re
from typing import Any, Dict, List

from ..json_store import DATA_DIR, read_doc, write_doc, with_lock, JsonStoreError

VARIANTS_PATH = DATA_DIR / "product_variants.json"
SKU_INDEX_PATH = DATA_DIR / "sku_index.json"
KEY_INDEX_PATH = DATA_DIR / "variant_key_index.json"
COUNTERS_PATH = DATA_DIR / "counters.json"

SKU_RE = re.compile(r"^\d+$")


def _norm_key(options: Dict[str, Any], param_order: List[str]) -> str:
    parts = []
    for pid in param_order:
        if pid in options:
            parts.append(f"{pid}={options[pid]}")
    return "|".join(parts)


def _next_variant_id() -> str:
    lock = with_lock("counters")
    lock.acquire()
    try:
        counters = read_doc(COUNTERS_PATH, default={"version": 1, "next_variant_id": 1})
        n = int(counters.get("next_variant_id", 1))
        counters["next_variant_id"] = n + 1
        write_doc(COUNTERS_PATH, counters)
        return f"variant_{n}"
    finally:
        lock.release()


def load_variants() -> Dict[str, Any]:
    return read_doc(VARIANTS_PATH, default={"version": 1, "items": []})


def save_variants(doc: Dict[str, Any]) -> None:
    write_doc(VARIANTS_PATH, doc)


def load_sku_index() -> Dict[str, Any]:
    return read_doc(SKU_INDEX_PATH, default={"version": 1, "sku_to_variant_id": {}})


def save_sku_index(doc: Dict[str, Any]) -> None:
    write_doc(SKU_INDEX_PATH, doc)


def load_key_index() -> Dict[str, Any]:
    return read_doc(KEY_INDEX_PATH, default={"version": 1, "product_to_keys": {}})


def save_key_index(doc: Dict[str, Any]) -> None:
    write_doc(KEY_INDEX_PATH, doc)


def generate_preview(
    product_id: str,
    selected_params: List[str],
    values_by_param: Dict[str, List[Any]],
) -> List[Dict[str, Any]]:
    param_order = selected_params[:]

    combos: List[Dict[str, Any]] = [{}]
    for pid in selected_params:
        vals = values_by_param.get(pid, [])
        if not vals:
            continue
        new_combos = []
        for base in combos:
            for v in vals:
                d = dict(base)
                d[pid] = v
                new_combos.append(d)
        combos = new_combos

    if not selected_params or not combos:
        combos = [{}]

    key_index = load_key_index()
    existing = key_index.get("product_to_keys", {}).get(product_id, {})

    preview = []
    for opt in combos:
        key = _norm_key(opt, param_order)
        exists = key in existing
        preview.append({
            "options": opt,
            "variant_key": key,
            "exists": exists,
            "enabled": not exists
        })
    return preview


def bulk_create_variants(
    product_id: str,
    rows: List[Dict[str, Any]],
    selected_params: List[str],
) -> Dict[str, Any]:
    lock = with_lock("variants_write")
    lock.acquire()
    try:
        variants_doc = load_variants()
        sku_doc = load_sku_index()
        key_doc = load_key_index()

        items: List[Dict[str, Any]] = variants_doc.get("items", [])
        sku_map: Dict[str, str] = sku_doc.get("sku_to_variant_id", {})
        product_keys: Dict[str, Dict[str, str]] = key_doc.get("product_to_keys", {})
        if product_id not in product_keys:
            product_keys[product_id] = {}

        created: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for idx, r in enumerate(rows):
            if not r.get("enabled", True):
                continue

            options = r.get("options", {}) or {}
            key = r.get("variant_key") or _norm_key(options, selected_params)

            if key in product_keys[product_id]:
                errors.append({"row": idx, "code": "DUPLICATE_VARIANT_KEY", "message": f"Комбинация уже существует: {key}"})
                continue

            sku = r.get("sku")
            if sku is not None and sku != "":
                sku_str = str(sku).strip()
                if not SKU_RE.match(sku_str):
                    errors.append({"row": idx, "code": "BAD_SKU", "message": f"SKU должен быть цифрами: {sku_str}"})
                    continue
                if sku_str in sku_map:
                    errors.append({"row": idx, "code": "DUPLICATE_SKU", "message": f"SKU уже используется: {sku_str}"})
                    continue
            else:
                sku_str = ""

            sku_pim = str(r.get("sku_pim") or "").strip()
            sku_gt = str(r.get("sku_gt") or "").strip()
            sku_id = str(r.get("sku_id") or "").strip()
            if sku_pim and not SKU_RE.match(sku_pim):
                errors.append({"row": idx, "code": "BAD_SKU_PIM", "message": f"SKU PIM должен быть цифрами: {sku_pim}"})
                continue
            if sku_gt and not SKU_RE.match(sku_gt):
                errors.append({"row": idx, "code": "BAD_SKU_GT", "message": f"SKU GT должен быть цифрами: {sku_gt}"})
                continue
            if sku_id and not SKU_RE.match(sku_id):
                errors.append({"row": idx, "code": "BAD_SKU_ID", "message": f"SKU ID должен быть цифрами: {sku_id}"})
                continue

            variant_id = _next_variant_id()
            obj = {
                "id": variant_id,
                "product_id": product_id,
                "sku": sku_str,
                "sku_pim": sku_pim,
                "sku_gt": sku_gt,
                "sku_id": sku_id,
                "title": str(r.get("title") or "").strip(),
                "links": r.get("links") or [],
                "content": r.get("content") or {},
                "options": options,
                "status": "active"
            }

            items.append(obj)
            product_keys[product_id][key] = variant_id
            if sku_str:
                sku_map[sku_str] = variant_id

            created.append(obj)

        variants_doc["items"] = items
        sku_doc["sku_to_variant_id"] = sku_map
        key_doc["product_to_keys"] = product_keys

        save_variants(variants_doc)
        save_sku_index(sku_doc)
        save_key_index(key_doc)

        return {"created": created, "errors": errors}
    finally:
        lock.release()


def update_variant_sku(variant_id: str, sku: str) -> Dict[str, Any]:
    lock = with_lock("variants_write")
    lock.acquire()
    try:
        variants_doc = load_variants()
        sku_doc = load_sku_index()

        items: List[Dict[str, Any]] = variants_doc.get("items", [])
        sku_map: Dict[str, str] = sku_doc.get("sku_to_variant_id", {})

        v = next((x for x in items if x.get("id") == variant_id), None)
        if not v:
            raise JsonStoreError("VARIANT_NOT_FOUND")

        new_sku = (sku or "").strip()
        if new_sku:
            if not SKU_RE.match(new_sku):
                raise JsonStoreError("BAD_SKU")
            owner = sku_map.get(new_sku)
            if owner and owner != variant_id:
                raise JsonStoreError("DUPLICATE_SKU")

        old_sku = (v.get("sku") or "").strip()
        if old_sku and sku_map.get(old_sku) == variant_id:
            sku_map.pop(old_sku, None)

        v["sku"] = new_sku
        if new_sku:
            sku_map[new_sku] = variant_id

        save_variants(variants_doc)
        save_sku_index(sku_doc)

        return v
    finally:
        lock.release()


def list_variants_by_product(product_id: str) -> List[Dict[str, Any]]:
    doc = load_variants()
    return [x for x in doc.get("items", []) if x.get("product_id") == product_id]
