from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.core.json_store import JsonStoreError
from app.storage.relational_pim_store import (
    allocate_next_product_identity,
    delete_product_items,
    find_product_by_sku_gt,
    load_products_by_category,
    load_products_by_group,
    load_products_by_ids,
    query_products_full,
    upsert_product_item,
)
from app.core.products.variants_repo import (
    bulk_create_variants as repo_bulk_create_variants,
    generate_preview as repo_generate_variants_preview,
    list_variants_by_product as repo_list_variants_by_product,
    update_variant_sku as repo_update_variant_sku,
)


BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
PRODUCTS_PATH = BASE_DIR / "data" / "products.json"


def _load_products_doc() -> Dict[str, Any]:
    return {"items": query_products_full()}


def _save_products_doc(doc: Dict[str, Any]) -> None:
    raise JsonStoreError("FULL_PRODUCTS_WRITE_DISABLED")


def _items() -> List[Dict[str, Any]]:
    doc = _load_products_doc()
    return [x for x in (doc.get("items") or []) if isinstance(x, dict)]


def _save_items(items: List[Dict[str, Any]]) -> None:
    _save_products_doc({"items": items})


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _parse_int(value: Any) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return 0


def _max_numeric(items: List[Dict[str, Any]], key: str, default: int) -> int:
    max_value = default
    for item in items:
        raw = _norm(item.get(key))
        if raw.isdigit():
            max_value = max(max_value, int(raw))
    return max_value


def _next_product_id(items: List[Dict[str, Any]]) -> str:
    max_idx = 0
    for item in items:
        pid = _norm(item.get("id"))
        if pid.startswith("product_"):
            suffix = pid.split("_", 1)[1]
            if suffix.isdigit():
                max_idx = max(max_idx, int(suffix))
    return f"product_{max_idx + 1}"


def _default_content() -> Dict[str, Any]:
    return {
        "features": [],
        "links": [],
        "media": [],
        "media_images": [],
        "media_videos": [],
        "media_cover": [],
        "description": "",
        "documents": [],
        "analogs": [],
        "related": [],
    }


def _ensure_unique_sku(items: List[Dict[str, Any]], *, sku_gt: str = "", exclude_id: str = "") -> None:
    for item in items:
        pid = _norm(item.get("id"))
        if exclude_id and pid == exclude_id:
            continue
        if sku_gt and _norm(item.get("sku_gt")) == sku_gt:
            raise JsonStoreError("DUPLICATE_SKU_GT")

def allocate_sku_pairs_service(count: int) -> Dict[str, Any]:
    qty = int(count or 0)
    if qty < 1:
        raise JsonStoreError("BAD_SKU")
    identity = allocate_next_product_identity()
    next_pim = _parse_int(identity.get("next_sku_pim"))
    next_gt = _parse_int(identity.get("next_sku_gt"))
    out: List[Dict[str, str]] = []
    for idx in range(qty):
        out.append(
            {
                "sku_pim": str(next_pim + idx),
                "sku_gt": str(next_gt + idx),
            }
        )
    return {"items": out, "count": len(out)}


def create_product_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    category_id = _norm(payload.get("category_id"))
    title = _norm(payload.get("title"))
    product_type = _norm(payload.get("type")) or "single"
    if not category_id:
        raise JsonStoreError("CATEGORY_REQUIRED")
    if not title:
        raise JsonStoreError("TITLE_REQUIRED")
    if product_type not in {"single", "multi"}:
        raise JsonStoreError("BAD_TYPE")

    items = query_products_full()
    sku_pim = _norm(payload.get("sku_pim"))
    sku_gt = _norm(payload.get("sku_gt"))
    if not sku_pim or not sku_gt:
        allocated = allocate_sku_pairs_service(1).get("items") or [{}]
        pair = allocated[0] if allocated else {}
        sku_pim = sku_pim or _norm(pair.get("sku_pim"))
        sku_gt = sku_gt or _norm(pair.get("sku_gt"))

    _ensure_unique_sku(items, sku_gt=sku_gt)

    product = {
        "id": _next_product_id(items),
        "category_id": category_id,
        "type": product_type,
        "status": _norm(payload.get("status")) or "draft",
        "title": title,
        "sku_pim": sku_pim,
        "sku_gt": sku_gt,
        "group_id": _norm(payload.get("group_id")) or None,
        "selected_params": list(payload.get("selected_params") or []),
        "feature_params": list(payload.get("feature_params") or []),
        "exports_enabled": dict(payload.get("exports_enabled") or {}),
        "content": _default_content(),
    }
    items.append(product)
    saved = upsert_product_item(product)
    return saved or product


def get_product_service(product_id: str, include_variants: bool = True) -> Dict[str, Any]:
    pid = _norm(product_id)
    items = load_products_by_ids([pid])
    product = next((x for x in items if _norm(x.get("id")) == pid), None)
    if not isinstance(product, dict):
        raise JsonStoreError("PRODUCT_NOT_FOUND")
    result: Dict[str, Any] = {"product": product}
    if include_variants:
        group_id = _norm(product.get("group_id"))
        if group_id:
            variants = [x for x in load_products_by_group(group_id) if _norm(x.get("id")) != pid]
        else:
            variants = []
        result["variants"] = variants
    return result


def get_products_bulk_service(product_ids: List[str]) -> Dict[str, Any]:
    wanted: Set[str] = {_norm(x) for x in (product_ids or []) if _norm(x)}
    if not wanted:
        return {"items": [], "count": 0}
    out = [item for item in load_products_by_ids(list(wanted)) if _norm(item.get("id")) in wanted]
    return {"items": out, "count": len(out)}


def patch_product_service(product_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    pid = _norm(product_id)
    items = query_products_full()
    target: Optional[Dict[str, Any]] = None
    for item in items:
        if _norm(item.get("id")) == pid:
            target = item
            break
    if not isinstance(target, dict):
        raise JsonStoreError("PRODUCT_NOT_FOUND")

    if "type" in patch:
        product_type = _norm(patch.get("type"))
        if product_type and product_type not in {"single", "multi"}:
            raise JsonStoreError("BAD_TYPE")
        if product_type:
            target["type"] = product_type

    if "status" in patch:
        status = _norm(patch.get("status"))
        if status and status not in {"draft", "active", "archive", "archived"}:
            raise JsonStoreError("BAD_STATUS")
        if status:
            target["status"] = "archive" if status == "archived" else status

    if "title" in patch:
        title = _norm(patch.get("title"))
        if not title:
            raise JsonStoreError("TITLE_REQUIRED")
        target["title"] = title

    sku_gt = _norm(patch.get("sku_gt")) if "sku_gt" in patch else _norm(target.get("sku_gt"))
    _ensure_unique_sku(items, sku_gt=sku_gt, exclude_id=pid)

    for key in ("category_id", "sku_pim", "sku_gt", "group_id"):
        if key in patch:
            target[key] = _norm(patch.get(key)) or None

    for key in ("selected_params", "feature_params"):
        if key in patch:
            target[key] = list(patch.get(key) or [])

    if "exports_enabled" in patch:
        target["exports_enabled"] = dict(patch.get("exports_enabled") or {})

    if "content" in patch:
        existing = target.get("content") if isinstance(target.get("content"), dict) else _default_content()
        incoming = patch.get("content") if isinstance(patch.get("content"), dict) else {}
        target["content"] = {**existing, **incoming}

    saved = upsert_product_item(target)
    return {"product": saved or target}


def list_products_by_category_service(category_id: str) -> Dict[str, Any]:
    cid = _norm(category_id)
    items = load_products_by_category(cid)
    return {"items": items, "count": len(items)}


def find_product_by_sku_service(sku_gt: Optional[str] = None) -> Dict[str, Any]:
    gt = _norm(sku_gt)
    product = find_product_by_sku_gt(gt)
    return {"product": product} if product else {}


def delete_products_bulk_service(ids: List[str]) -> Dict[str, Any]:
    id_set: Set[str] = {_norm(x) for x in (ids or []) if _norm(x)}
    if not id_set:
        return {"ok": True, "deleted": 0, "ids": []}
    items = load_products_by_ids(list(id_set))
    deleted_ids = [_norm(x.get("id")) for x in items if _norm(x.get("id")) in id_set]
    deleted = delete_product_items(list(id_set))
    return {"ok": True, "deleted": len(deleted_ids), "ids": deleted_ids}


def generate_variants_preview_service(product_id: str, selected_params: List[str], values_by_param: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    return repo_generate_variants_preview(product_id, selected_params, values_by_param)


def bulk_create_variants_service(product_id: str, rows: List[Dict[str, Any]], selected_params: List[str]) -> Dict[str, Any]:
    return repo_bulk_create_variants(product_id, rows, selected_params)


def update_variant_sku_service(variant_id: str, sku: str) -> Dict[str, Any]:
    variant = repo_update_variant_sku(variant_id, sku)
    return {"variant": variant}


def list_variants_by_product_service(product_id: str) -> Dict[str, Any]:
    items = repo_list_variants_by_product(product_id)
    return {"items": items}
