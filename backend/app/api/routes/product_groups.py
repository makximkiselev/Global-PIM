from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.json_store import DATA_DIR, read_doc, write_doc, with_lock
from app.core.products.repo import load_products
from app.storage.json_store import load_dictionaries_db, load_templates_db

router = APIRouter(prefix="/product-groups", tags=["product-groups"])

GROUPS_PATH = DATA_DIR / "product_groups.json"
COUNTERS_PATH = DATA_DIR / "counters.json"
CATALOG_NODES_PATH = DATA_DIR / "catalog_nodes.json"
SERVICE_CODES = {"sku_pim", "sku_gt", "barcode", "group_id", "title"}
PRODUCTS_PATH = DATA_DIR / "products.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_groups() -> Dict[str, Any]:
    return read_doc(GROUPS_PATH, default={"version": 1, "items": []})


def _save_groups(doc: Dict[str, Any]) -> None:
    write_doc(GROUPS_PATH, doc)


def _next_group_id() -> str:
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
                "next_group_id": 1,
            },
        )
        n = int(counters.get("next_group_id", 1))
        counters["next_group_id"] = n + 1
        write_doc(COUNTERS_PATH, counters)
        return f"group_{n}"
    finally:
        lock.release()


def _product_summary(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(p.get("id") or ""),
        "title": str(p.get("title") or p.get("name") or ""),
        "sku_pim": str(p.get("sku_pim") or ""),
        "sku_gt": str(p.get("sku_gt") or ""),
        "group_id": str(p.get("group_id") or ""),
        "category_id": str(p.get("category_id") or ""),
    }


def _sort_key_group_name(name: str) -> str:
    return str(name or "").strip().lower()


def _sort_key_sku_gt(value: str) -> Tuple[int, int, str]:
    s = str(value or "").strip()
    if not s:
        return (1, 0, "")
    if s.isdigit():
        return (0, int(s), s)
    # Alphanumeric GT IDs go after purely numeric, lexicographically.
    return (0, 10**18, s.lower())


def _sort_key_path(path: str) -> str:
    return str(path or "").strip().lower()


def _get_group(doc: Dict[str, Any], group_id: str) -> Dict[str, Any]:
    for g in doc.get("items", []) or []:
        if str(g.get("id")) == group_id:
            return g
    raise HTTPException(status_code=404, detail="GROUP_NOT_FOUND")


def _normalize_ids(items: Any) -> List[str]:
    if not isinstance(items, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for x in items:
        s = str(x or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _ensure_group_shape(group: Dict[str, Any]) -> Dict[str, Any]:
    group["variant_param_ids"] = _normalize_ids(group.get("variant_param_ids") or [])
    return group


def _sync_group_feature_names(
    items: List[Dict[str, Any]],
    *,
    group_id: str,
    group_name: str,
    remove_for_product_ids: Optional[Set[str]] = None,
) -> int:
    changed = 0
    remove_for_product_ids = remove_for_product_ids or set()
    target_group_id = str(group_id or "").strip()
    target_group_name = str(group_name or "").strip()
    for product in items:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or "").strip()
        content = product.get("content") if isinstance(product.get("content"), dict) else None
        if not isinstance(content, dict):
            continue
        features = content.get("features") if isinstance(content.get("features"), list) else []
        if not isinstance(features, list):
            continue
        for feature in features:
            if not isinstance(feature, dict):
                continue
            code = str(feature.get("code") or "").strip().lower()
            name = str(feature.get("name") or "").strip().lower()
            if code != "group_id" and "группа товара" not in name:
                continue
            next_value = ""
            if pid not in remove_for_product_ids and str(product.get("group_id") or "").strip() == target_group_id and target_group_name:
                next_value = target_group_name
            if str(feature.get("value") or "").strip() != next_value:
                feature["value"] = next_value
                changed += 1
            source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
            yandex_sources = source_values.get("yandex_market") if isinstance(source_values.get("yandex_market"), dict) else {}
            if isinstance(yandex_sources, dict) and yandex_sources:
                yandex_changed = False
                for payload in yandex_sources.values():
                    if not isinstance(payload, dict):
                        continue
                    if str(payload.get("canonical_value") or "").strip() != next_value:
                        payload["canonical_value"] = next_value
                        yandex_changed = True
                    if str(payload.get("resolved_value") or "").strip() != next_value:
                        payload["resolved_value"] = next_value
                        yandex_changed = True
                if yandex_changed:
                    source_values["yandex_market"] = yandex_sources
                    feature["source_values"] = source_values
                    changed += 1
    return changed


def _load_nodes() -> List[Dict[str, Any]]:
    doc = read_doc(CATALOG_NODES_PATH, default=[])
    return doc if isinstance(doc, list) else []


def _templates_by_category(db: Dict[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    templates = db.get("templates") or {}

    if isinstance(templates, dict):
        for tid, t in templates.items():
            if not isinstance(t, dict):
                continue
            cid = str(t.get("category_id") or "").strip()
            if not cid:
                continue
            out.setdefault(cid, [])
            sid = str(tid)
            if sid not in out[cid]:
                out[cid].append(sid)

    cat_to_tpls = db.get("category_to_templates") or {}
    if isinstance(cat_to_tpls, dict):
        for cid, arr in cat_to_tpls.items():
            if not isinstance(arr, list):
                continue
            out.setdefault(str(cid), [])
            for tid in arr:
                sid = str(tid or "").strip()
                if sid and sid not in out[str(cid)]:
                    out[str(cid)].append(sid)

    return out


def _resolve_template_ids_for_category(
    category_id: str,
    category_to_templates: Dict[str, List[str]],
    parent_by_id: Dict[str, Optional[str]],
) -> Tuple[List[str], Optional[str]]:
    cur = category_id
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        tids = category_to_templates.get(cur, []) or []
        if tids:
            return tids, cur
        cur = str(parent_by_id.get(cur) or "")
    return [], None


@router.get("")
def list_groups() -> Dict[str, Any]:
    doc = _load_groups()
    items = doc.get("items", []) or []
    products_doc = load_products()
    products = products_doc.get("items", []) or []
    counts: Dict[str, int] = {}
    group_categories: Dict[str, List[str]] = {}
    for p in products:
        gid = str(p.get("group_id") or "").strip()
        if not gid:
            continue
        counts[gid] = counts.get(gid, 0) + 1
        cid = str(p.get("category_id") or "").strip()
        if cid:
            group_categories.setdefault(gid, []).append(cid)

    nodes = _load_nodes()
    node_by_id: Dict[str, Dict[str, Any]] = {}
    parent_by_id: Dict[str, Optional[str]] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        if not nid:
            continue
        node_by_id[nid] = n
        pid = str(n.get("parent_id") or "").strip()
        parent_by_id[nid] = pid or None

    def root_category_id(category_id: str) -> str:
        cur = str(category_id or "").strip()
        seen: Set[str] = set()
        last = cur
        while cur and cur not in seen:
            seen.add(cur)
            last = cur
            cur = str(parent_by_id.get(cur) or "").strip()
        return last

    def category_path(category_id: str) -> str:
        cur = str(category_id or "").strip()
        if not cur:
            return ""
        chain: List[str] = []
        seen: Set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            node = node_by_id.get(cur, {})
            chain.append(str(node.get("name") or cur))
            cur = str(parent_by_id.get(cur) or "").strip()
        chain.reverse()
        return " / ".join([x for x in chain if x])

    def dominant_root_for_group(group_id: str) -> Tuple[Optional[str], Optional[str]]:
        cat_ids = group_categories.get(group_id) or []
        if not cat_ids:
            return None, None
        freq: Dict[str, int] = {}
        for cid in cat_ids:
            rid = root_category_id(cid)
            if rid:
                freq[rid] = freq.get(rid, 0) + 1
        if not freq:
            return None, None
        top = sorted(freq.items(), key=lambda x: (-x[1], str(node_by_id.get(x[0], {}).get("name") or "").lower(), x[0]))[0][0]
        rname = str(node_by_id.get(top, {}).get("name") or "").strip() or top
        return top, rname

    def dominant_category_for_group(group_id: str) -> Tuple[Optional[str], Optional[str]]:
        cat_ids = group_categories.get(group_id) or []
        if not cat_ids:
            return None, None
        freq: Dict[str, int] = {}
        for cid in cat_ids:
            s = str(cid or "").strip()
            if s:
                freq[s] = freq.get(s, 0) + 1
        if not freq:
            return None, None
        top = sorted(freq.items(), key=lambda x: (-x[1], _sort_key_path(category_path(x[0])), x[0]))[0][0]
        return top, category_path(top)

    out = []
    for g in items:
        gid = str(g.get("id") or "")
        gg = _ensure_group_shape(dict(g))
        root_id, root_name = dominant_root_for_group(gid)
        cat_id, cat_path = dominant_category_for_group(gid)
        root_node = node_by_id.get(str(root_id or ""), {})
        root_position = int(root_node.get("position") or 10**9)
        out.append(
            {
                "id": gid,
                "name": str(g.get("name") or ""),
                "count": int(counts.get(gid, 0)),
                "variant_param_ids": gg.get("variant_param_ids") or [],
                "root_category_id": root_id,
                "root_category_name": root_name,
                "root_position": root_position,
                "category_id": cat_id,
                "category_path": cat_path,
            }
        )
    out.sort(key=lambda x: _sort_key_group_name(str(x.get("name") or "")))
    return {"items": out}


@router.get("/ungrouped")
def list_ungrouped() -> Dict[str, Any]:
    products_doc = load_products()
    products = products_doc.get("items", []) or []
    items = [_product_summary(p) for p in products if not str(p.get("group_id") or "").strip()]
    items.sort(key=lambda x: (x.get("title") or "").lower())
    return {"items": items}


@router.get("/{group_id}")
def group_details(group_id: str) -> Dict[str, Any]:
    doc = _load_groups()
    group = _ensure_group_shape(_get_group(doc, group_id))
    products_doc = load_products()
    products = products_doc.get("items", []) or []
    items = [_product_summary(p) for p in products if str(p.get("group_id") or "") == group_id]
    items.sort(
        key=lambda x: (
            _sort_key_sku_gt(str(x.get("sku_gt") or "")),
            _sort_key_group_name(str(x.get("title") or "")),
        )
    )
    return {"group": group, "items": items}


class GroupCreateReq(BaseModel):
    name: str = Field(min_length=1)
    variant_param_ids: List[str] = Field(default_factory=list)


@router.post("")
def create_group(req: GroupCreateReq) -> Dict[str, Any]:
    doc = _load_groups()
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="NAME_REQUIRED")

    gid = _next_group_id()
    now = _now_iso()
    group = {
        "id": gid,
        "name": name,
        "variant_param_ids": _normalize_ids(req.variant_param_ids),
        "created_at": now,
        "updated_at": now,
    }
    items = doc.get("items", []) or []
    items.append(group)
    doc["items"] = items
    _save_groups(doc)
    return {"group": group}


class GroupPatchReq(BaseModel):
    name: Optional[str] = None
    variant_param_ids: Optional[List[str]] = None


@router.patch("/{group_id}")
def patch_group(group_id: str, req: GroupPatchReq) -> Dict[str, Any]:
    doc = _load_groups()
    group = _get_group(doc, group_id)
    if req.name is not None:
        name = req.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="NAME_REQUIRED")
        group["name"] = name
    if req.variant_param_ids is not None:
        group["variant_param_ids"] = _normalize_ids(req.variant_param_ids)
    group["updated_at"] = _now_iso()
    _save_groups(doc)
    if req.name is not None:
        lock = with_lock("products_write")
        lock.acquire()
        try:
            products_doc = load_products()
            items = products_doc.get("items", []) or []
            if _sync_group_feature_names(items, group_id=group_id, group_name=str(group.get("name") or "").strip()):
                products_doc["items"] = items
                write_doc(PRODUCTS_PATH, products_doc)
        finally:
            lock.release()
    return {"group": _ensure_group_shape(group)}


class GroupItemsPatchReq(BaseModel):
    add: List[str] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)


@router.post("/{group_id}/items")
def patch_group_items(group_id: str, req: GroupItemsPatchReq) -> Dict[str, Any]:
    doc = _load_groups()
    group = _ensure_group_shape(_get_group(doc, group_id))

    lock = with_lock("products_write")
    lock.acquire()
    try:
        products_doc = load_products()
        items = products_doc.get("items", []) or []
        add_set = {str(x) for x in req.add or [] if str(x).strip()}
        remove_set = {str(x) for x in req.remove or [] if str(x).strip()}

        changed = 0
        for p in items:
            pid = str(p.get("id") or "")
            if pid in add_set:
                p["group_id"] = group_id
                p["type"] = "multi"
                changed += 1
            if pid in remove_set and str(p.get("group_id") or "") == group_id:
                p.pop("group_id", None)
                p["type"] = "single"
                changed += 1

        changed += _sync_group_feature_names(
            items,
            group_id=group_id,
            group_name=str(group.get("name") or "").strip(),
            remove_for_product_ids=remove_set,
        )

        products_doc["items"] = items
        write_doc(PRODUCTS_PATH, products_doc)
    finally:
        lock.release()

    return {"ok": True, "changed": changed}


@router.get("/{group_id}/variant-params")
def list_group_variant_params(group_id: str) -> Dict[str, Any]:
    groups_doc = _load_groups()
    group = _ensure_group_shape(_get_group(groups_doc, group_id))
    selected_set = set(group.get("variant_param_ids") or [])

    products_doc = load_products()
    products = products_doc.get("items", []) or []
    group_products = [p for p in products if str(p.get("group_id") or "") == group_id]

    category_ids = sorted(
        {str(p.get("category_id") or "").strip() for p in group_products if str(p.get("category_id") or "").strip()}
    )

    templates_db = load_templates_db()
    dict_db = load_dictionaries_db()
    templates = templates_db.get("templates") if isinstance(templates_db.get("templates"), dict) else {}
    attrs_by_template = templates_db.get("attributes") if isinstance(templates_db.get("attributes"), dict) else {}
    category_to_templates = _templates_by_category(templates_db)

    dict_items = dict_db.get("items") if isinstance(dict_db.get("items"), list) else []
    dict_meta_by_id: Dict[str, Dict[str, Any]] = {}
    for d in dict_items:
        if not isinstance(d, dict):
            continue
        did = str(d.get("id") or "").strip()
        if not did:
            continue
        dict_meta_by_id[did] = d

    nodes = _load_nodes()
    parent_by_id: Dict[str, Optional[str]] = {}
    for n in nodes:
        cid = str(n.get("id") or "").strip()
        if not cid:
            continue
        pid = str(n.get("parent_id") or "").strip()
        parent_by_id[cid] = pid or None

    out_by_id: Dict[str, Dict[str, Any]] = {}
    for category_id in category_ids:
        tids, source_category_id = _resolve_template_ids_for_category(category_id, category_to_templates, parent_by_id)
        for tid in tids:
            attrs = attrs_by_template.get(tid, []) if isinstance(attrs_by_template.get(tid), list) else []
            for a in attrs:
                if not isinstance(a, dict):
                    continue
                if str(a.get("scope") or "").strip().lower() != "variant":
                    continue

                code = str(a.get("code") or "").strip()
                options = a.get("options") if isinstance(a.get("options"), dict) else {}
                dict_id = str(options.get("dict_id") or "").strip()
                if not dict_id and code:
                    dict_id = f"dict_{code}"

                dmeta = dict_meta_by_id.get(dict_id, {}) if dict_id else {}
                meta = dmeta.get("meta") if isinstance(dmeta.get("meta"), dict) else {}
                is_service = (code.lower() in SERVICE_CODES) or bool(meta.get("service"))
                if is_service:
                    continue

                pid = dict_id or str(options.get("attribute_id") or a.get("id") or code)
                pid = pid.strip()
                if not pid:
                    continue

                row = out_by_id.get(pid)
                if not row:
                    row = {
                        "id": pid,
                        "name": str(a.get("name") or code or pid),
                        "code": code,
                        "scope": str(a.get("scope") or ""),
                        "type": str(a.get("type") or ""),
                        "dict_id": dict_id or None,
                        "category_ids": [],
                        "source_category_ids": [],
                        "template_ids": [],
                        "selected": pid in selected_set,
                    }
                    out_by_id[pid] = row

                if category_id not in row["category_ids"]:
                    row["category_ids"].append(category_id)
                if source_category_id and source_category_id not in row["source_category_ids"]:
                    row["source_category_ids"].append(source_category_id)
                if tid not in row["template_ids"]:
                    row["template_ids"].append(tid)

    items = list(out_by_id.values())
    items.sort(key=lambda x: (str(x.get("name") or "").lower(), str(x.get("code") or "").lower()))
    return {"items": items, "selected_ids": group.get("variant_param_ids") or []}
