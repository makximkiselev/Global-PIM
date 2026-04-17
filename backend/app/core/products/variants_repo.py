from __future__ import annotations

import re
from typing import Any, Dict, List

from ..json_store import with_lock, JsonStoreError
from app.storage.relational_pim_store import (
    allocate_next_variant_identity,
    find_product_variant,
    find_product_variant_by_sku,
    insert_product_variants,
    list_product_variants,
    update_product_variant_sku,
)

SKU_RE = re.compile(r"^\d+$")


def _norm_key(options: Dict[str, Any], param_order: List[str]) -> str:
    parts = []
    for pid in param_order:
        if pid in options:
            parts.append(f"{pid}={options[pid]}")
    return "|".join(parts)


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

    existing = {_norm_key(v.get("options") if isinstance(v.get("options"), dict) else {}, param_order): str(v.get("id") or "").strip() for v in list_product_variants(product_id)}

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
        items = list_product_variants(product_id)
        sku_map: Dict[str, str] = {}
        product_keys: Dict[str, str] = {}
        for item in items:
            existing_sku = str(item.get("sku") or "").strip()
            existing_id = str(item.get("id") or "").strip()
            if existing_sku and existing_id:
                sku_map[existing_sku] = existing_id
            product_keys[_norm_key(item.get("options") if isinstance(item.get("options"), dict) else {}, selected_params)] = existing_id

        created: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        rows_to_insert: List[Dict[str, Any]] = []

        for idx, r in enumerate(rows):
            if not r.get("enabled", True):
                continue

            options = r.get("options", {}) or {}
            key = r.get("variant_key") or _norm_key(options, selected_params)

            if key in product_keys:
                errors.append({"row": idx, "code": "DUPLICATE_VARIANT_KEY", "message": f"Комбинация уже существует: {key}"})
                continue

            sku = r.get("sku")
            if sku is not None and sku != "":
                sku_str = str(sku).strip()
                if not SKU_RE.match(sku_str):
                    errors.append({"row": idx, "code": "BAD_SKU", "message": f"SKU должен быть цифрами: {sku_str}"})
                    continue
                if sku_str in sku_map or find_product_variant_by_sku(sku_str):
                    errors.append({"row": idx, "code": "DUPLICATE_SKU", "message": f"SKU уже используется: {sku_str}"})
                    continue
            else:
                sku_str = ""

            sku_pim = str(r.get("sku_pim") or "").strip()
            sku_gt = str(r.get("sku_gt") or "").strip()
            if sku_pim and not SKU_RE.match(sku_pim):
                errors.append({"row": idx, "code": "BAD_SKU_PIM", "message": f"SKU PIM должен быть цифрами: {sku_pim}"})
                continue
            if sku_gt and not SKU_RE.match(sku_gt):
                errors.append({"row": idx, "code": "BAD_SKU_GT", "message": f"SKU GT должен быть цифрами: {sku_gt}"})
                continue

            variant_id = allocate_next_variant_identity()
            obj = {
                "id": variant_id,
                "product_id": product_id,
                "sku": sku_str,
                "sku_pim": sku_pim,
                "sku_gt": sku_gt,
                "title": str(r.get("title") or "").strip(),
                "links": r.get("links") or [],
                "content": r.get("content") or {},
                "options": options,
                "status": "active"
            }
            product_keys[key] = variant_id
            if sku_str:
                sku_map[sku_str] = variant_id
            created.append(obj)
            rows_to_insert.append(obj)

        if rows_to_insert:
            insert_product_variants(rows_to_insert)

        return {"created": created, "errors": errors}
    finally:
        lock.release()


def update_variant_sku(variant_id: str, sku: str) -> Dict[str, Any]:
    lock = with_lock("variants_write")
    lock.acquire()
    try:
        v = find_product_variant(variant_id)
        if not v:
            raise JsonStoreError("VARIANT_NOT_FOUND")

        new_sku = (sku or "").strip()
        if new_sku:
            if not SKU_RE.match(new_sku):
                raise JsonStoreError("BAD_SKU")
            owner = find_product_variant_by_sku(new_sku)
            if owner and str(owner.get("id") or "").strip() != variant_id:
                raise JsonStoreError("DUPLICATE_SKU")
        updated = update_product_variant_sku(variant_id, new_sku)
        if not updated:
            raise JsonStoreError("VARIANT_NOT_FOUND")
        return updated
    finally:
        lock.release()


def list_variants_by_product(product_id: str) -> List[Dict[str, Any]]:
    return list_product_variants(product_id)
