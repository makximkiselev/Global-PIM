from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from datetime import datetime, timezone

from app.core.json_store import JsonStoreError, with_lock
from app.storage.relational_pim_store import (
    allocate_next_product_identity,
    bulk_upsert_product_items,
    delete_product_items,
    find_product_by_sku_gt,
    load_catalog_nodes,
    load_category_template_resolution_map,
    load_template_editor_payload,
    load_product_groups_doc,
    load_products_by_category,
    load_products_by_group,
    load_products_by_ids,
    load_templates_db_doc,
    query_products_full,
    save_product_groups_doc,
    update_product_media_images,
    upsert_product_item,
)
from app.core.master_templates import base_field_by_code, base_field_by_name
from app.core.tenant_context import current_tenant_organization_id
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_ids(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for item in items:
        value = _norm(item)
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _next_group_id_from_doc(groups_doc: Dict[str, Any]) -> str:
    max_idx = 0
    for group in groups_doc.get("items", []) or []:
        if not isinstance(group, dict):
            continue
        gid = _norm(group.get("id"))
        if gid.startswith("group_"):
            suffix = gid.split("_", 1)[1]
            if suffix.isdigit():
                max_idx = max(max_idx, int(suffix))
    return f"group_{max_idx + 1}"


def _content_payload(value: Any) -> Dict[str, Any]:
    base = _default_content()
    incoming = value if isinstance(value, dict) else {}
    return {**base, **incoming}


def _infer_brand_from_title(title: Any) -> str:
    normalized = _norm(title).lower()
    if not normalized:
        return ""
    brands = ["Apple", "Samsung", "Google", "Huawei", "Sony", "Dyson", "Nintendo", "Microsoft", "Meta", "Oculus", "Oura", "Яндекс"]
    for brand in brands:
        if brand.lower() in normalized:
            return brand
    return ""


def _template_attributes_for_category(category_id: str) -> List[Dict[str, Any]]:
    cid = _norm(category_id)
    if not cid:
        return []
    organization_id = current_tenant_organization_id()
    db = load_templates_db_doc(organization_id)
    template_ids = []
    category_to_templates = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    direct_ids = category_to_templates.get(cid) if isinstance(category_to_templates.get(cid), list) else []
    template_ids.extend([_norm(tid) for tid in direct_ids if _norm(tid)])

    if not template_ids:
        resolution = load_category_template_resolution_map(organization_id).get(cid) or {}
        resolved_id = _norm(resolution.get("template_id"))
        if resolved_id:
            template_ids.append(resolved_id)

    templates_available = bool(db.get("templates") if isinstance(db.get("templates"), dict) else {})

    if not template_ids and templates_available:
        nodes = load_catalog_nodes()
        by_id = {str(node.get("id") or "").strip(): node for node in nodes if isinstance(node, dict)}
        path_ids: List[str] = []
        seen: Set[str] = set()
        cur = by_id.get(cid)
        while cur:
            node_id = _norm(cur.get("id"))
            if not node_id or node_id in seen:
                break
            seen.add(node_id)
            path_ids.append(node_id)
            parent_id = _norm(cur.get("parent_id"))
            cur = by_id.get(parent_id) if parent_id else None
        path_ids.reverse()
        if path_ids:
            payload = load_template_editor_payload(path_ids, organization_id)
            tpl = payload.get("template") if isinstance(payload.get("template"), dict) else {}
            template_id = _norm(tpl.get("id"))
            if template_id:
                template_ids.append(template_id)

    attrs_by_template = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for template_id in template_ids:
        for attr in attrs_by_template.get(template_id, []) or []:
            if not isinstance(attr, dict):
                continue
            code = _norm(attr.get("code") or attr.get("name"))
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(dict(attr))
    return out


def _canonical_feature_identity(feature: Dict[str, Any]) -> Dict[str, str]:
    code = _norm(feature.get("code"))
    name = _norm(feature.get("name") or code)
    field_layer = _norm(feature.get("field_layer")) or _norm((feature.get("options") if isinstance(feature.get("options"), dict) else {}).get("field_layer"))
    if code.startswith("raw_") or field_layer == "raw_competitor":
        return {"key": f"raw:{code or name}", "code": code, "name": name}

    base = base_field_by_code(code) if code else None
    if not base:
        base = base_field_by_name(name) if name else None
    if base:
        base_code = _norm(base.get("code"))
        base_name = _norm(base.get("name"))
        return {"key": f"base:{base_code}", "code": base_code, "name": base_name}

    key = _norm_lower(code or name)
    return {"key": f"feature:{key}", "code": code, "name": name}


def _merge_source_values(target: Dict[str, Any], incoming: Dict[str, Any]) -> None:
    incoming_sources = incoming.get("source_values") if isinstance(incoming.get("source_values"), dict) else {}
    if not incoming_sources:
        return
    target_sources = target.get("source_values") if isinstance(target.get("source_values"), dict) else {}
    for source_key, source_value in incoming_sources.items():
        if isinstance(source_value, dict) and isinstance(target_sources.get(source_key), dict):
            target_sources[source_key] = {**target_sources[source_key], **source_value}
        else:
            target_sources[source_key] = source_value
    target["source_values"] = target_sources


def _dedupe_product_features(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    by_key: Dict[str, Dict[str, Any]] = {}
    for raw_feature in features:
        if not isinstance(raw_feature, dict):
            continue
        feature = dict(raw_feature)
        identity = _canonical_feature_identity(feature)
        key = identity["key"]
        if key.startswith("raw:"):
            continue
        if identity.get("code"):
            feature["code"] = identity["code"]
        if identity.get("name"):
            feature["name"] = identity["name"]
        existing = by_key.get(key)
        if not existing:
            by_key[key] = feature
            out.append(feature)
            continue
        if not _norm(existing.get("value")) and _norm(feature.get("value")):
            existing["value"] = _norm(feature.get("value"))
        _merge_source_values(existing, feature)
        for meta_key in ("type", "required", "scope", "param_group", "field_layer", "fill_source", "locked"):
            if meta_key not in existing or existing.get(meta_key) in (None, ""):
                if feature.get(meta_key) not in (None, ""):
                    existing[meta_key] = feature.get(meta_key)
    return out


def _fill_system_feature_value(product: Dict[str, Any], content: Dict[str, Any], feature: Dict[str, Any]) -> None:
    if not isinstance(feature, dict) or _norm(feature.get("value")):
        return
    code_key = _norm_lower(feature.get("code") or feature.get("name"))
    options = feature.get("options") if isinstance(feature.get("options"), dict) else {}
    system_key = _norm(options.get("system_key"))
    if code_key == "бренд" or code_key == "brand" or system_key == "brand":
        feature["value"] = _infer_brand_from_title(product.get("title"))
    elif code_key == "sku_gt" or system_key == "sku_gt":
        feature["value"] = _norm(product.get("sku_gt"))
    elif code_key == "sku_pim" or system_key == "sku_pim":
        feature["value"] = _norm(product.get("sku_pim"))
    elif code_key in {"наименование_товара", "title"} or system_key == "title":
        feature["value"] = _norm(product.get("title"))
    elif system_key == "description":
        feature["value"] = _norm(content.get("description"))


def _info_model_context_for_category(category_id: str) -> Dict[str, Any]:
    cid = _norm(category_id)
    empty = {
        "has_template": False,
        "template_id": "",
        "template_ids": [],
        "template_name": "",
        "status": "",
        "attributes_count": 0,
        "attributes": [],
    }
    if not cid:
        return empty

    organization_id = current_tenant_organization_id()
    db = load_templates_db_doc(organization_id)
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    attrs_by_template = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    category_to_templates = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    templates_available = bool(templates)

    template_ids = [
        _norm(tid)
        for tid in (category_to_templates.get(cid) if isinstance(category_to_templates.get(cid), list) else [])
        if _norm(tid)
    ]
    if not template_ids:
        resolution = load_category_template_resolution_map(organization_id).get(cid) or {}
        resolved_id = _norm(resolution.get("template_id"))
        if resolved_id:
            template_ids.append(resolved_id)

    if not template_ids and templates_available:
        nodes = load_catalog_nodes()
        by_id = {str(node.get("id") or "").strip(): node for node in nodes if isinstance(node, dict)}
        path_ids: List[str] = []
        seen: Set[str] = set()
        cur = by_id.get(cid)
        while cur:
            node_id = _norm(cur.get("id"))
            if not node_id or node_id in seen:
                break
            seen.add(node_id)
            path_ids.append(node_id)
            parent_id = _norm(cur.get("parent_id"))
            cur = by_id.get(parent_id) if parent_id else None
        path_ids.reverse()
        if path_ids:
            payload = load_template_editor_payload(path_ids, organization_id)
            tpl = payload.get("template") if isinstance(payload.get("template"), dict) else {}
            template_id = _norm(tpl.get("id"))
            if template_id:
                template_ids.append(template_id)

    template_ids = [tid for tid in template_ids if isinstance(templates.get(tid), dict)]
    if not template_ids:
        return empty

    template_id = template_ids[0]
    template = templates.get(template_id) or {}
    attrs = [dict(attr) for attr in (attrs_by_template.get(template_id) or []) if isinstance(attr, dict)]
    meta = template.get("meta") if isinstance(template.get("meta"), dict) else {}
    info_model = meta.get("info_model") if isinstance(meta.get("info_model"), dict) else {}

    return {
        "has_template": True,
        "template_id": template_id,
        "template_ids": template_ids,
        "template_name": _norm(template.get("name")) or template_id,
        "status": _norm(info_model.get("status")) or _norm(template.get("status")),
        "attributes_count": len(attrs),
        "attributes": [
            {
                "code": _norm(attr.get("code") or attr.get("name")),
                "name": _norm(attr.get("name") or attr.get("code")),
                "required": bool(attr.get("required", False)),
                "type": _norm(attr.get("type")) or "text",
                "scope": _norm(attr.get("scope")),
                "param_group": _norm((attr.get("options") if isinstance(attr.get("options"), dict) else {}).get("param_group")),
                "field_layer": _norm((attr.get("options") if isinstance(attr.get("options"), dict) else {}).get("field_layer")) or ("system" if bool(attr.get("locked")) else "features"),
                "fill_source": _norm((attr.get("options") if isinstance(attr.get("options"), dict) else {}).get("fill_source")) or ("system" if bool(attr.get("locked")) else "manual"),
                "locked": bool(attr.get("locked", False)),
            }
            for attr in attrs
        ],
    }


def seed_product_features_from_category(product: Dict[str, Any]) -> Dict[str, Any]:
    content = _content_payload(product.get("content"))
    existing_features = content.get("features") if isinstance(content.get("features"), list) else []
    features: List[Dict[str, Any]] = _dedupe_product_features([dict(item) for item in existing_features if isinstance(item, dict)])
    for feature in features:
        _fill_system_feature_value(product, content, feature)
        feature_options = feature.get("options") if isinstance(feature.get("options"), dict) else {}
        if bool(feature.get("locked")) or _norm(feature.get("field_layer")) == "system" or _norm(feature_options.get("field_layer")) == "system":
            feature["locked"] = True

    attrs = _template_attributes_for_category(_norm(product.get("category_id")))
    existing_keys = {_canonical_feature_identity(feature)["key"] for feature in features}
    for attr in attrs:
        code = _norm(attr.get("code") or attr.get("name"))
        name = _norm(attr.get("name") or code)
        if not code or not name:
            continue
        options = attr.get("options") if isinstance(attr.get("options"), dict) else {}
        system_key = _norm(options.get("system_key"))
        value = ""
        if system_key == "sku_gt":
            value = _norm(product.get("sku_gt"))
        elif system_key == "sku_pim":
            value = _norm(product.get("sku_pim"))
        elif system_key == "title":
            value = _norm(product.get("title"))
        elif system_key == "brand":
            value = _infer_brand_from_title(product.get("title"))
        elif system_key == "description":
            value = _norm(content.get("description"))

        next_feature = {
            "code": code,
            "name": name,
            "value": value,
            "type": _norm(attr.get("type")) or "text",
            "required": bool(attr.get("required", False)),
            "scope": _norm(attr.get("scope")),
            "param_group": _norm(options.get("param_group")),
            "field_layer": _norm(options.get("field_layer")) or ("system" if bool(attr.get("locked")) else "features"),
            "fill_source": _norm(options.get("fill_source")) or ("system" if bool(attr.get("locked")) else "manual"),
            "locked": bool(attr.get("locked")),
            "source_values": {},
        }
        identity = _canonical_feature_identity(next_feature)
        if identity["key"] in existing_keys:
            continue
        features.append(next_feature)
        existing_keys.add(identity["key"])

    if features:
        content["features"] = _dedupe_product_features(features)
    product["content"] = content
    return product

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
    seed_product_features_from_category(product)
    items.append(product)
    saved = upsert_product_item(product)
    return saved or product


def create_product_family_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    category_id = _norm(payload.get("category_id"))
    product_type = _norm(payload.get("type")) or "single"
    group_name = _norm(payload.get("title")) or _norm(payload.get("group_name"))
    selected_params = _normalize_ids(payload.get("selected_params") or [])
    feature_params = _normalize_ids(payload.get("feature_params") or [])
    exports_enabled = dict(payload.get("exports_enabled") or {})
    variants = payload.get("variants") if isinstance(payload.get("variants"), list) else []

    if not category_id:
        raise JsonStoreError("CATEGORY_REQUIRED")
    if product_type not in {"single", "multi"}:
        raise JsonStoreError("BAD_TYPE")
    if not variants:
        raise JsonStoreError("TITLE_REQUIRED")
    if product_type == "single" and len(variants) != 1:
        raise JsonStoreError("BAD_TYPE")
    if product_type == "multi" and not group_name:
        raise JsonStoreError("TITLE_REQUIRED")

    lock = with_lock("products_family_create")
    lock.acquire()
    saved_group_doc: Optional[Dict[str, Any]] = None
    try:
        existing = query_products_full()
        existing_skus = {_norm(item.get("sku_gt")) for item in existing if _norm(item.get("sku_gt"))}
        next_identity = allocate_next_product_identity()
        next_product_num = _parse_int(str(next_identity.get("product_id") or "").replace("product_", ""))
        next_pim = _parse_int(next_identity.get("next_sku_pim"))
        next_gt = _parse_int(next_identity.get("next_sku_gt"))

        groups_doc = load_product_groups_doc()
        group_id: Optional[str] = None
        group: Optional[Dict[str, Any]] = None
        if product_type == "multi":
            group_id = _next_group_id_from_doc(groups_doc)
            now = _now_iso()
            group = {
                "id": group_id,
                "name": group_name,
                "variant_param_ids": selected_params,
                "created_at": now,
                "updated_at": now,
            }
            saved_group_doc = groups_doc
            next_groups_doc = {
                **groups_doc,
                "items": list(groups_doc.get("items", []) or []) + [group],
            }
            save_product_groups_doc(next_groups_doc)

        products: List[Dict[str, Any]] = []
        seen_skus: Set[str] = set()
        for idx, raw_variant in enumerate(variants):
            variant = raw_variant if isinstance(raw_variant, dict) else {}
            title = _norm(variant.get("title"))
            if not title:
                raise JsonStoreError("TITLE_REQUIRED")

            sku_pim = _norm(variant.get("sku_pim")) or str(next_pim + idx)
            sku_gt = _norm(variant.get("sku_gt")) or str(next_gt + idx)
            if not sku_gt:
                raise JsonStoreError("BAD_SKU")
            if sku_gt in existing_skus or sku_gt in seen_skus:
                raise JsonStoreError("DUPLICATE_SKU_GT")
            seen_skus.add(sku_gt)

            products.append(
                {
                    "id": f"product_{next_product_num + idx}",
                    "category_id": category_id,
                    "type": product_type,
                    "status": _norm(variant.get("status")) or "draft",
                    "title": title,
                    "sku_pim": sku_pim,
                    "sku_gt": sku_gt,
                    "group_id": group_id,
                    "selected_params": selected_params if product_type == "multi" else [],
                    "feature_params": feature_params,
                    "exports_enabled": dict(variant.get("exports_enabled") or exports_enabled),
                    "content": _content_payload(variant.get("content")),
                }
            )
            seed_product_features_from_category(products[-1])

        saved_products = bulk_upsert_product_items(products)
        return {
            "ok": True,
            "group": group,
            "products": saved_products or products,
            "count": len(saved_products or products),
            "first_product": (saved_products or products)[0] if products else None,
        }
    except Exception:
        if saved_group_doc is not None:
            try:
                save_product_groups_doc(saved_group_doc)
            except Exception:
                pass
        raise
    finally:
        lock.release()


def get_product_service(product_id: str, include_variants: bool = True) -> Dict[str, Any]:
    pid = _norm(product_id)
    items = load_products_by_ids([pid])
    product = next((x for x in items if _norm(x.get("id")) == pid), None)
    if not isinstance(product, dict):
        raise JsonStoreError("PRODUCT_NOT_FOUND")
    result: Dict[str, Any] = {
        "product": product,
        "info_model": _info_model_context_for_category(_norm(product.get("category_id"))),
    }
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
            target["status"] = "archived" if status == "archive" else status

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


def patch_product_media_images_service(product_id: str, media_images: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_media: List[Dict[str, Any]] = []
    for index, item in enumerate(media_images or []):
        if not isinstance(item, dict):
            continue
        url = _norm(item.get("url"))
        if not url:
            continue
        normalized = dict(item)
        normalized["url"] = url
        normalized["order"] = index
        normalized["export_order"] = index
        normalized_media.append(normalized)
    saved = update_product_media_images(product_id, normalized_media)
    if not saved:
        raise JsonStoreError("PRODUCT_NOT_FOUND")
    return {"product": saved}


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
