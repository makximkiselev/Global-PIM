from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.json_store import read_doc, write_doc
from app.storage.relational_pim_store import load_catalog_nodes, query_products_full

router = APIRouter(prefix="/marketplaces/ozon", tags=["marketplaces-ozon"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data" / "marketplaces" / "ozon"
ENV_PATH = BASE_DIR / ".env"
MARKETPLACES_DIR = BASE_DIR / "data" / "marketplaces"
CONNECTORS_STATE_PATH = MARKETPLACES_DIR / "connectors_scheduler.json"
PRODUCTS_PATH = BASE_DIR / "data" / "products.json"
CATALOG_NODES_PATH = BASE_DIR / "data" / "catalog_nodes.json"

CATEGORIES_TREE_PATH = DATA_DIR / "categories_tree.json"
CATEGORY_ATTRS_PATH = DATA_DIR / "category_attributes.json"
CATEGORY_ATTR_VALUES_PATH = DATA_DIR / "attribute_values.json"
PRODUCT_RATING_PATH = DATA_DIR / "product_rating_by_sku.json"
IMPORT_INFO_PATH = DATA_DIR / "import_products_info.json"
OZON_API_BASE = "https://api-seller.ozon.ru"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_file_value(key: str) -> str:
    if not ENV_PATH.exists():
        return ""
    try:
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            if k.strip() != key:
                continue
            val = v.strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            return val.strip()
    except Exception:
        return ""
    return ""


def _env_api_key() -> str:
    return (
        os.getenv("OZON_ACCESS_TOKEN", "").strip()
        or os.getenv("OZON_API_KEY", "").strip()
        or os.getenv("OZON_TOKEN", "").strip()
        or _env_file_value("OZON_ACCESS_TOKEN")
        or _env_file_value("OZON_API_KEY")
        or _env_file_value("OZON_TOKEN")
    )


def _env_client_id() -> str:
    return os.getenv("OZON_CLIENT_ID", "").strip() or _env_file_value("OZON_CLIENT_ID")


def _env_secondary_api_key() -> str:
    return (
        os.getenv("OZON_ACCESS_TOKEN_SECONDARY", "").strip()
        or os.getenv("OZON_API_KEY_SECONDARY", "").strip()
        or os.getenv("OZON_TOKEN_SECONDARY", "").strip()
        or _env_file_value("OZON_ACCESS_TOKEN_SECONDARY")
        or _env_file_value("OZON_API_KEY_SECONDARY")
        or _env_file_value("OZON_TOKEN_SECONDARY")
    )


def _env_secondary_client_id() -> str:
    return os.getenv("OZON_CLIENT_ID_SECONDARY", "").strip() or _env_file_value("OZON_CLIENT_ID_SECONDARY")


def _env_auth_mode() -> str:
    return (
        os.getenv("OZON_AUTH_MODE", "").strip().lower()
        or _env_file_value("OZON_AUTH_MODE").lower()
        or "auto"
    )


def _to_str_id(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _load_products() -> List[Dict[str, Any]]:
    return query_products_full()


def _save_doc(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_doc(path, payload)


def _load_nodes() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _default_import_store_credentials() -> Dict[str, Any]:
    state = read_doc(CONNECTORS_STATE_PATH, default={"providers": {}})
    providers = state.get("providers") if isinstance(state, dict) else {}
    if not isinstance(providers, dict):
        return {}
    prow = providers.get("ozon")
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    if isinstance(stores, list):
        for store in stores:
            if not isinstance(store, dict):
                continue
            if not bool(store.get("enabled")):
                continue
            if str(store.get("client_id") or "").strip() and str(store.get("api_key") or "").strip():
                return store
    return {}


def _extract_text_list(values: Any) -> List[str]:
    if values is None:
        return []
    if isinstance(values, str):
        s = values.strip()
        return [s] if s else []
    if not isinstance(values, list):
        return []
    out: List[str] = []
    seen = set()
    for x in values:
        if isinstance(x, dict):
            v = str(x.get("value") or x.get("name") or x.get("title") or "").strip()
        else:
            v = str(x or "").strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _normalize_tree(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = raw.get("result") if isinstance(raw, dict) else None
    roots: List[Any] = []
    if isinstance(result, list):
        roots = result
    elif isinstance(result, dict):
        if isinstance(result.get("items"), list):
            roots = result.get("items") or []
        elif isinstance(result.get("categories"), list):
            roots = result.get("categories") or []
        elif isinstance(result.get("children"), list):
            roots = result.get("children") or []

    out: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], parent_id: Optional[str], depth: int, path: List[str], parent_category_id: Optional[str]) -> None:
        if not isinstance(node, dict):
            return
        nid = (
            _to_str_id(node.get("description_category_id"))
            or _to_str_id(node.get("category_id"))
            or _to_str_id(node.get("id"))
        )
        type_id = _to_str_id(node.get("type_id"))
        type_name = str(node.get("type_name") or "").strip()
        name = str(node.get("category_name") or node.get("name") or node.get("title") or type_name).strip()

        node_kind = "category"
        category_id_for_node: Optional[str] = None
        type_id_for_node: Optional[str] = None
        if nid:
            node_kind = "category"
            category_id_for_node = nid
        elif type_id:
            if not parent_category_id:
                return
            nid = f"type:{parent_category_id}:{type_id}"
            node_kind = "type"
            category_id_for_node = parent_category_id
            type_id_for_node = type_id
        else:
            return

        children = node.get("children")
        if not isinstance(children, list):
            children = node.get("items")
        if not isinstance(children, list):
            children = []

        cur_path = [*path, name or nid]
        out.append(
            {
                "id": nid,
                "name": name,
                "parent_id": parent_id,
                "depth": depth,
                "path": " / ".join([x for x in cur_path if x]),
                "is_leaf": len(children) == 0,
                "node_kind": node_kind,
                "category_id": category_id_for_node,
                "type_id": type_id_for_node,
            }
        )
        for child in children:
            next_parent_category_id = category_id_for_node if node_kind == "category" else parent_category_id
            walk(child, nid, depth + 1, cur_path, next_parent_category_id)

    for root in roots:
        walk(root, None, 0, [], None)
    return out


def _parse_ozon_category_ref(category_ref: str) -> Tuple[str, Optional[int]]:
    ref = str(category_ref or "").strip()
    if not ref:
        return "", None
    if ref.startswith("type:"):
        parts = ref.split(":")
        # type:{category_id}:{type_id}
        if len(parts) >= 3:
            cat_id = str(parts[1] or "").strip()
            tid_raw = str(parts[2] or "").strip()
            if cat_id and tid_raw.isdigit():
                return cat_id, int(tid_raw)
    return ref, None


def _normalize_attributes(raw: Dict[str, Any], source_type_id: Optional[int] = None) -> List[Dict[str, Any]]:
    result = raw.get("result") if isinstance(raw, dict) else None
    items: List[Any] = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        if isinstance(result.get("attributes"), list):
            items = result.get("attributes") or []
        elif isinstance(result.get("items"), list):
            items = result.get("items") or []

    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, dict):
            continue
        aid = (
            _to_str_id(x.get("id"))
            or _to_str_id(x.get("attribute_id"))
        )
        name = str(x.get("name") or x.get("attribute_name") or "").strip()
        if not aid and not name:
            continue
        out.append(
            {
                "id": aid or name,
                "name": name or aid,
                "required": bool(x.get("is_required") or x.get("required") or False),
                "type": str(x.get("type") or x.get("value_type") or "").strip(),
                "dictionary_id": int(x.get("dictionary_id") or 0) if str(x.get("dictionary_id") or "").strip().isdigit() else 0,
                "type_id": int(source_type_id or 0) if source_type_id else 0,
            }
        )
    return out


def _extract_values_from_result(result: Any) -> List[str]:
    items: List[Any] = []
    if isinstance(result, list):
        items = result
    elif isinstance(result, dict):
        if isinstance(result.get("values"), list):
            items = result.get("values") or []
        elif isinstance(result.get("items"), list):
            items = result.get("items") or []

    out: List[str] = []
    for v in items:
        if isinstance(v, str):
            s = v.strip()
            if s:
                out.append(s)
            continue
        if isinstance(v, (int, float)):
            out.append(str(v))
            continue
        if not isinstance(v, dict):
            continue
        for key in ("value", "name", "title", "label"):
            s = str(v.get(key) or "").strip()
            if s:
                out.append(s)
                break
    return out


def _extract_last_value_id(result: Any) -> Optional[int]:
    if isinstance(result, dict):
        for key in ("last_value_id", "last_id"):
            v = result.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
        items = result.get("values")
        if not isinstance(items, list):
            items = result.get("items")
    elif isinstance(result, list):
        items = result
    else:
        items = None

    if isinstance(items, list) and items:
        last = items[-1]
        if isinstance(last, dict):
            for key in ("id", "value_id"):
                v = last.get(key)
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.strip().isdigit():
                    return int(v.strip())
    return None


async def _fetch_attribute_values_all_pages(
    *,
    category_id: str,
    type_id: int,
    attribute_id: int,
    language: str,
    limit: int,
    last_value_id: Optional[int],
    max_pages: int,
    token: str,
    client_id: str,
) -> Dict[str, Any]:
    seen: Set[str] = set()
    values: List[str] = []
    pages_raw: List[Dict[str, Any]] = []
    has_next_any = False
    cursor = last_value_id

    for _ in range(max(1, int(max_pages))):
        payload: Dict[str, Any] = {
            "description_category_id": int(category_id) if category_id.isdigit() else category_id,
            "type_id": int(type_id),
            "attribute_id": int(attribute_id),
            "language": language,
            "limit": int(limit),
        }
        if cursor is not None:
            payload["last_value_id"] = int(cursor)

        res = await _post_with_auth_modes("/v1/description-category/attribute/values", payload, token, client_id)
        body = res.json() if res.content else {}
        if isinstance(body, dict):
            pages_raw.append(body)

        result = body.get("result") if isinstance(body, dict) else {}
        page_vals = _extract_values_from_result(result)
        for s in page_vals:
            if s not in seen:
                seen.add(s)
                values.append(s)

        has_next = bool(body.get("has_next")) if isinstance(body, dict) else False
        if not has_next and isinstance(result, dict):
            has_next = bool(result.get("has_next"))

        if not has_next:
            break
        has_next_any = True
        next_cursor = _extract_last_value_id(result)
        if next_cursor is None:
            break
        cursor = int(next_cursor)

    return {"values": values, "raw_pages": pages_raw, "has_next": has_next_any}


def _tree_roots(raw_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = raw_doc.get("result") if isinstance(raw_doc, dict) else None
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        for k in ("items", "categories", "children"):
            v = result.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def _resolve_type_ids(description_category_id: str) -> List[int]:
    doc = read_doc(CATEGORIES_TREE_PATH, default={})
    raw = doc.get("raw") if isinstance(doc, dict) else {}
    roots = _tree_roots(raw if isinstance(raw, dict) else {})
    if not roots:
        return []

    target = str(description_category_id or "").strip()
    if not target:
        return []

    type_ids: List[int] = []

    def collect_types(node: Dict[str, Any]) -> None:
        if not isinstance(node, dict):
            return
        tid = node.get("type_id")
        if isinstance(tid, int) and tid > 0:
            type_ids.append(tid)
        elif isinstance(tid, str) and tid.strip().isdigit():
            type_ids.append(int(tid.strip()))
        children = node.get("children")
        if not isinstance(children, list):
            children = node.get("items")
        if not isinstance(children, list):
            children = []
        for child in children:
            if isinstance(child, dict):
                collect_types(child)

    def find_and_collect(node: Dict[str, Any]) -> bool:
        if not isinstance(node, dict):
            return False
        nid = _to_str_id(node.get("description_category_id") or node.get("category_id") or node.get("id"))
        if nid == target:
            collect_types(node)
            return True
        children = node.get("children")
        if not isinstance(children, list):
            children = node.get("items")
        if not isinstance(children, list):
            children = []
        for child in children:
            if isinstance(child, dict) and find_and_collect(child):
                return True
        return False

    for root in roots:
        if find_and_collect(root):
            break
    return sorted(set([x for x in type_ids if isinstance(x, int) and x > 0]))


class ImportCategoriesReq(BaseModel):
    language: str = Field(default="DEFAULT")
    token: Optional[str] = None
    client_id: Optional[str] = None


class ImportCategoryAttrsReq(BaseModel):
    category_id: str = Field(min_length=1)
    language: str = Field(default="DEFAULT")
    type_id: Optional[int] = None
    import_values: bool = True
    values_limit: int = Field(default=200, ge=1, le=5000)
    values_max_pages: int = Field(default=3, ge=1, le=200)
    force_values_refresh: bool = False
    token: Optional[str] = None
    client_id: Optional[str] = None


class ImportAttributeValuesReq(BaseModel):
    category_id: str = Field(min_length=1)
    attribute_id: int
    type_id: Optional[int] = None
    language: str = Field(default="DEFAULT")
    limit: int = Field(default=500, ge=1, le=5000)
    last_value_id: Optional[int] = None
    token: Optional[str] = None
    client_id: Optional[str] = None


class OzonProductsSyncReq(BaseModel):
    category_id: Optional[str] = None
    product_ids: List[str] = Field(default_factory=list)
    include_descendants: bool = True
    limit: int = Field(default=500, ge=1, le=20000)
    token: Optional[str] = None
    client_id: Optional[str] = None
    store_id: Optional[str] = None
    store_title: Optional[str] = None


def _auth_headers_for_mode(mode: str, token: str, client_id: str, errors: List[str]) -> Optional[Dict[str, str]]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if mode == "api-key":
        if not client_id:
            errors.append("[api-key] OZON_CLIENT_ID_MISSING")
            return None
        headers["Client-Id"] = client_id
        headers["Api-Key"] = token
    else:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _post_with_auth_modes(path: str, payload: Dict[str, Any], token: str, client_id: str) -> httpx.Response:
    auth_mode = _env_auth_mode()
    modes = [auth_mode] if auth_mode in {"api-key", "bearer"} else ["bearer", "api-key"]
    errors: List[str] = []
    res: Optional[httpx.Response] = None
    for mode in modes:
        headers = _auth_headers_for_mode(mode, token, client_id, errors)
        if headers is None:
            continue
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(f"{OZON_API_BASE}{path}", json=payload, headers=headers)
            if res.is_success:
                return res
            errors.append(f"[{mode}] {res.status_code}: {res.text[:260]}")
        except Exception as e:
            errors.append(f"[{mode}] {e}")
    tail = " | ".join(errors[-6:]) if errors else "NO_RESPONSE"
    raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED {tail}")


async def _fetch_categories_tree_raw(language: str, token: str, client_id: str) -> Dict[str, Any]:
    payloads: List[Dict[str, Any]] = [{"language": language}, {}]
    errors: List[str] = []
    for payload in payloads:
        try:
            res = await _post_with_auth_modes("/v1/description-category/tree", payload, token, client_id)
            body = res.json() if res.content else {}
            if isinstance(body, dict):
                return body
            return {}
        except HTTPException as e:
            ptag = "with-language" if payload else "empty-body"
            errors.append(f"[{ptag}] {e.detail}")
        except Exception as e:
            ptag = "with-language" if payload else "empty-body"
            errors.append(f"[{ptag}] {e}")
    tail = " | ".join(errors[-6:]) if errors else "NO_RESPONSE"
    raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED {tail}")


async def probe_store_access(*, api_key: str, client_id: str) -> Dict[str, Any]:
    token = str(api_key or "").strip()
    cid = str(client_id or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="OZON_API_KEY_MISSING")
    if not cid:
        raise HTTPException(status_code=400, detail="OZON_CLIENT_ID_MISSING")
    raw = await _fetch_categories_tree_raw("DEFAULT", token, cid)
    roots = _tree_roots(raw if isinstance(raw, dict) else {})
    return {"ok": True, "client_id": cid, "roots_count": len(roots)}


async def _post_api_key(path: str, payload: Dict[str, Any], api_key: str, client_id: str) -> Dict[str, Any]:
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(f"{OZON_API_BASE}{path}", json=payload, headers=headers)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED {e}")
    if not res.is_success:
        raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED [{res.status_code}] {res.text[:500]}")
    return res.json() if res.content else {}


def _merge_flat_categories(flats: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for flat in flats:
        for row in flat or []:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id") or "").strip()
            if not rid:
                continue
            prev = by_id.get(rid)
            if prev is None:
                by_id[rid] = dict(row)
                continue
            # Keep deeper/longer path record if available.
            prev_depth = int(prev.get("depth") or 0)
            cur_depth = int(row.get("depth") or 0)
            prev_path = str(prev.get("path") or "")
            cur_path = str(row.get("path") or "")
            if cur_depth > prev_depth or len(cur_path) > len(prev_path):
                by_id[rid] = dict(row)
    out = list(by_id.values())
    out.sort(key=lambda x: (str(x.get("path") or x.get("name") or "").lower(), str(x.get("id") or "")))
    return out


def _tree_roots_for_merge(raw_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = raw_doc.get("result") if isinstance(raw_doc, dict) else None
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if isinstance(result, dict):
        for key in ("items", "categories", "children"):
            v = result.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


@router.post("/import/categories-tree")
async def import_categories_tree(req: ImportCategoriesReq) -> Dict[str, Any]:
    token_primary = (req.token or "").strip() or _env_api_key()
    if not token_primary:
        raise HTTPException(status_code=400, detail="OZON_API_KEY_MISSING")

    client_primary = (req.client_id or "").strip() or _env_client_id()
    token_secondary = _env_secondary_api_key()
    client_secondary = _env_secondary_client_id()
    language = (req.language or "DEFAULT").strip().upper()

    creds: List[Tuple[str, str, str]] = [("primary", token_primary, client_primary)]
    if token_secondary:
        creds.append(("secondary", token_secondary, client_secondary))
    # Dedupe identical credential pairs.
    uniq: List[Tuple[str, str, str]] = []
    seen_pairs: Set[str] = set()
    for label, tok, cid in creds:
        key = f"{tok}::{cid}"
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        uniq.append((label, tok, cid))
    creds = uniq

    all_roots: List[Dict[str, Any]] = []
    all_flats: List[List[Dict[str, Any]]] = []
    imported_sources: List[str] = []
    source_errors: List[str] = []

    for label, tok, cid in creds:
        try:
            raw = await _fetch_categories_tree_raw(language, tok, cid)
            flat_part = _normalize_tree(raw if isinstance(raw, dict) else {})
            all_roots.extend(_tree_roots_for_merge(raw if isinstance(raw, dict) else {}))
            all_flats.append(flat_part)
            imported_sources.append(label)
        except Exception as e:
            source_errors.append(f"{label}: {e}")
            continue

    if not all_flats:
        tail = " | ".join(source_errors[-6:]) if source_errors else "NO_RESPONSE"
        raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED {tail}")

    body = {"result": all_roots}
    flat = _merge_flat_categories(all_flats)
    doc = {
        "imported_at": _now_iso(),
        "language": language,
        "raw": body,
        "flat": flat,
        "count": len(flat),
        "sources_used": imported_sources,
        "sources_errors": source_errors,
    }
    write_doc(CATEGORIES_TREE_PATH, doc)
    return {
        "ok": True,
        "count": len(flat),
        "imported_at": doc["imported_at"],
        "sources_used": imported_sources,
        "sources_errors": source_errors,
    }


@router.post("/import/category-attributes")
async def import_category_attributes(req: ImportCategoryAttrsReq) -> Dict[str, Any]:
    token = (req.token or "").strip() or _env_api_key()
    if not token:
        raise HTTPException(status_code=400, detail="OZON_API_KEY_MISSING")

    client_id = (req.client_id or "").strip() or _env_client_id()
    category_id_raw = _to_str_id(req.category_id)
    category_id, parsed_type_id = _parse_ozon_category_ref(category_id_raw)
    if not category_id:
        raise HTTPException(status_code=400, detail="CATEGORY_ID_REQUIRED")
    language = (req.language or "DEFAULT").strip().upper()
    resolved_type_ids: List[int] = []
    if req.type_id is not None and int(req.type_id) > 0:
        resolved_type_ids = [int(req.type_id)]
    elif parsed_type_id is not None and int(parsed_type_id) > 0:
        resolved_type_ids = [int(parsed_type_id)]
    else:
        resolved_type_ids = _resolve_type_ids(category_id)

    payload_base: Dict[str, Any] = {
        "description_category_id": int(category_id) if category_id.isdigit() else category_id,
        "language": language,
    }
    payloads: List[Dict[str, Any]] = []
    for tid in resolved_type_ids:
        payloads.append({**payload_base, "type_id": int(tid)})
    if not payloads:
        payloads = [dict(payload_base)]

    attrs_by_id: Dict[str, Dict[str, Any]] = {}
    value_targets: Set[Tuple[int, int]] = set()
    raw_responses: List[Dict[str, Any]] = []
    used_types: List[int] = []
    request_errors: List[str] = []
    for payload in payloads:
        try:
            res = await _post_with_auth_modes("/v1/description-category/attribute", payload, token, client_id)
            body = res.json() if res.content else {}
            raw_responses.append({"payload": payload, "response": body})
            cur_type_id = int(payload.get("type_id")) if isinstance(payload.get("type_id"), int) else None
            attrs = _normalize_attributes(body if isinstance(body, dict) else {}, cur_type_id)
            for a in attrs:
                key = _to_str_id(a.get("id"))
                if not key:
                    continue
                attrs_by_id[key] = a
                aid = str(a.get("id") or "").strip()
                did = int(a.get("dictionary_id") or 0)
                tid = int(a.get("type_id") or 0)
                if did > 0 and tid > 0 and aid.isdigit():
                    value_targets.add((tid, int(aid)))
            if isinstance(payload.get("type_id"), int):
                used_types.append(int(payload["type_id"]))
        except HTTPException as e:
            request_errors.append(str(e.detail))
            continue

    if not attrs_by_id:
        tail = " | ".join(request_errors[-4:]) if request_errors else "NO_ATTRIBUTES"
        raise HTTPException(status_code=502, detail=f"OZON_HTTP_FAILED {tail}")

    values_errors: List[str] = []
    imported_values = 0
    skipped_values = 0
    if req.import_values and value_targets:
        values_doc = read_doc(CATEGORY_ATTR_VALUES_PATH, default={"items": {}})
        if not isinstance(values_doc, dict):
            values_doc = {"items": {}}
        if not isinstance(values_doc.get("items"), dict):
            values_doc["items"] = {}

        for tid, aid in sorted(value_targets):
            key = f"{category_id}:{tid}:{aid}"
            if not req.force_values_refresh:
                existing = values_doc["items"].get(key)
                if isinstance(existing, dict):
                    existing_vals = _extract_text_list(existing.get("values"))
                    if existing_vals:
                        skipped_values += 1
                        continue
            try:
                fetched = await _fetch_attribute_values_all_pages(
                    category_id=category_id,
                    type_id=tid,
                    attribute_id=aid,
                    language=language,
                    limit=int(req.values_limit),
                    last_value_id=None,
                    max_pages=int(req.values_max_pages),
                    token=token,
                    client_id=client_id,
                )
                values_doc["items"][key] = {
                    "category_id": category_id,
                    "type_id": tid,
                    "attribute_id": aid,
                    "imported_at": _now_iso(),
                    "language": language,
                    "limit": int(req.values_limit),
                    "last_value_id": None,
                    "values": fetched.get("values") or [],
                    "raw": {"pages": fetched.get("raw_pages") or []},
                }
                imported_values += 1
            except Exception as e:
                values_errors.append(str(e))
                continue
        write_doc(CATEGORY_ATTR_VALUES_PATH, values_doc)

    doc = read_doc(CATEGORY_ATTRS_PATH, default={"items": {}})
    if not isinstance(doc, dict):
        doc = {"items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    cache_key = category_id
    doc["items"][cache_key] = {
        "category_id": category_id,
        "imported_at": _now_iso(),
        "language": language,
        "type_ids": used_types,
        "attributes": list(attrs_by_id.values()),
        "raw": {"requests": raw_responses, "errors": request_errors, "values_errors": values_errors},
    }
    write_doc(CATEGORY_ATTRS_PATH, doc)
    return {
        "ok": True,
        "category_id": category_id_raw,
        "resolved_category_id": category_id,
        "type_ids_used": used_types,
        "attributes_count": len(attrs_by_id),
        "values_imported": imported_values,
        "values_skipped_cached": skipped_values,
    }


@router.post("/import/attribute-values")
async def import_attribute_values(req: ImportAttributeValuesReq) -> Dict[str, Any]:
    token = (req.token or "").strip() or _env_api_key()
    if not token:
        raise HTTPException(status_code=400, detail="OZON_API_KEY_MISSING")

    client_id = (req.client_id or "").strip() or _env_client_id()
    category_id_raw = _to_str_id(req.category_id)
    category_id, parsed_type_id = _parse_ozon_category_ref(category_id_raw)
    if not category_id:
        raise HTTPException(status_code=400, detail="CATEGORY_ID_REQUIRED")
    language = (req.language or "DEFAULT").strip().upper()

    resolved_type_ids: List[int] = []
    if req.type_id is not None and int(req.type_id) > 0:
        resolved_type_ids = [int(req.type_id)]
    elif parsed_type_id is not None and int(parsed_type_id) > 0:
        resolved_type_ids = [int(parsed_type_id)]
    else:
        resolved_type_ids = _resolve_type_ids(category_id)
    if not resolved_type_ids:
        raise HTTPException(status_code=400, detail="OZON_TYPE_ID_NOT_RESOLVED")

    used_type_id = int(resolved_type_ids[0])
    fetched = await _fetch_attribute_values_all_pages(
        category_id=category_id,
        type_id=used_type_id,
        attribute_id=int(req.attribute_id),
        language=language,
        limit=int(req.limit),
        last_value_id=req.last_value_id,
        max_pages=40,
        token=token,
        client_id=client_id,
    )

    doc = read_doc(CATEGORY_ATTR_VALUES_PATH, default={"items": {}})
    if not isinstance(doc, dict):
        doc = {"items": {}}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    key = f"{category_id}:{used_type_id}:{int(req.attribute_id)}"
    doc["items"][key] = {
        "category_id": category_id,
        "type_id": used_type_id,
        "attribute_id": int(req.attribute_id),
        "imported_at": _now_iso(),
        "language": language,
        "limit": int(req.limit),
        "last_value_id": req.last_value_id,
        "values": fetched.get("values") or [],
        "raw": {"pages": fetched.get("raw_pages") or []},
    }
    write_doc(CATEGORY_ATTR_VALUES_PATH, doc)
    return {"ok": True, "key": key, "values_count": len(fetched.get("values") or [])}


@router.get("/categories/tree")
def get_categories_tree() -> Dict[str, Any]:
    doc = read_doc(CATEGORIES_TREE_PATH, default={})
    return {
        "ok": True,
        "imported_at": doc.get("imported_at"),
        "language": doc.get("language"),
        "count": int(doc.get("count") or 0),
        "raw": doc.get("raw") or {},
    }


@router.get("/categories/flat")
def get_categories_flat() -> Dict[str, Any]:
    doc = read_doc(CATEGORIES_TREE_PATH, default={})
    return {
        "ok": True,
        "imported_at": doc.get("imported_at"),
        "language": doc.get("language"),
        "count": int(doc.get("count") or 0),
        "items": doc.get("flat") or [],
    }


@router.get("/category-attributes/{category_id}")
def get_category_attributes(category_id: str) -> Dict[str, Any]:
    doc = read_doc(CATEGORY_ATTRS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    row = items.get(str(category_id))
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="CATEGORY_ATTRIBUTES_NOT_FOUND")
    return {"ok": True, "item": row}


@router.get("/attribute-values")
def list_attribute_values() -> Dict[str, Any]:
    doc = read_doc(CATEGORY_ATTR_VALUES_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}
    out: List[Dict[str, Any]] = []
    for key, row in items.items():
        if not isinstance(row, dict):
            continue
        vals = row.get("values") if isinstance(row.get("values"), list) else []
        out.append(
            {
                "key": str(key),
                "category_id": row.get("category_id"),
                "type_id": row.get("type_id"),
                "attribute_id": row.get("attribute_id"),
                "imported_at": row.get("imported_at"),
                "values_count": len(vals),
            }
        )
    out.sort(key=lambda x: str(x.get("key") or ""))
    return {"ok": True, "items": out, "count": len(out)}


@router.post("/products/sync")
async def sync_product_statuses(req: OzonProductsSyncReq) -> Dict[str, Any]:
    store_creds = _default_import_store_credentials()
    api_key = (req.token or "").strip() or str(store_creds.get("api_key") or "").strip() or _env_api_key()
    client_id = (req.client_id or "").strip() or str(store_creds.get("client_id") or "").strip() or _env_client_id()
    if not api_key:
        raise HTTPException(status_code=400, detail="OZON_API_KEY_MISSING")
    if not client_id:
        raise HTTPException(status_code=400, detail="OZON_CLIENT_ID_MISSING")

    store_id = str(req.store_id or "").strip() or str(store_creds.get("id") or "").strip() or client_id
    store_title = str(req.store_title or "").strip() or str(store_creds.get("title") or "").strip() or store_id

    products = _load_products()
    target_ids: Set[str] = {str(x or "").strip() for x in (req.product_ids or []) if str(x or "").strip()}
    if req.category_id:
        nodes = _load_nodes()
        children: Dict[str, List[str]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            pid = str(node.get("parent_id") or "").strip()
            nid = str(node.get("id") or "").strip()
            if nid:
                children.setdefault(pid, []).append(nid)
        stack = [str(req.category_id or "").strip()]
        seen_categories: Set[str] = set()
        while stack:
            cid = stack.pop()
            if not cid or cid in seen_categories:
                continue
            seen_categories.add(cid)
            if req.include_descendants:
                stack.extend(children.get(cid, []))
        for product in products:
            if not isinstance(product, dict):
                continue
            if str(product.get("category_id") or "").strip() in seen_categories:
                pid = str(product.get("id") or "").strip()
                if pid:
                    target_ids.add(pid)

    selected: List[Dict[str, Any]] = []
    offer_to_product: Dict[str, Dict[str, Any]] = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or "").strip()
        if target_ids and pid not in target_ids:
            continue
        candidates = [str(product.get("sku_gt") or "").strip()]
        has_any = False
        for offer_id in candidates:
            if not offer_id:
                continue
            offer_to_product.setdefault(offer_id, product)
            has_any = True
        if has_any:
            selected.append(product)
        if len(selected) >= int(req.limit):
            break

    if not offer_to_product:
        return {"ok": True, "count": 0, "matched_products": 0, "stores": [{"store_id": store_id, "store_title": store_title}], "items": []}

    info_doc = read_doc(IMPORT_INFO_PATH, default={"items": {}})
    info_items = info_doc.get("items") if isinstance(info_doc, dict) else {}
    if not isinstance(info_items, dict):
        info_items = {}
    rating_doc = read_doc(PRODUCT_RATING_PATH, default={"items": {}})
    rating_items = rating_doc.get("items") if isinstance(rating_doc, dict) else {}
    if not isinstance(rating_items, dict):
        rating_items = {}

    found_items: List[Dict[str, Any]] = []
    sku_to_offer: Dict[str, str] = {}
    offer_ids = list(offer_to_product.keys())
    for start in range(0, len(offer_ids), 100):
        chunk = offer_ids[start:start + 100]
        body = await _post_api_key("/v3/product/info/list", {"offer_id": chunk}, api_key, client_id)
        items = body.get("items") if isinstance(body, dict) else []
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            offer_id = str(item.get("offer_id") or "").strip()
            if not offer_id:
                continue
            product = offer_to_product.get(offer_id)
            if not isinstance(product, dict):
                continue
            pid = str(product.get("id") or "").strip()
            status_obj = item.get("statuses") if isinstance(item.get("statuses"), dict) else {}
            sku_value = item.get("sku")
            if not str(sku_value or "").strip():
                sources = item.get("sources") if isinstance(item.get("sources"), list) else []
                for source in sources:
                    if isinstance(source, dict) and str(source.get("sku") or "").strip():
                        sku_value = source.get("sku")
                        break
            if str(sku_value or "").strip():
                sku_to_offer[str(sku_value)] = offer_id
            info_items[f"{store_id}:{offer_id}"] = {
                "store_id": store_id,
                "store_title": store_title,
                "client_id": client_id,
                "offer_id": offer_id,
                "product_id": pid or None,
                "sku": sku_value,
                "status": str(status_obj.get("status_name") or status_obj.get("status") or "").strip(),
                "state": str(status_obj.get("status") or "").strip(),
                "moderate_status": str(status_obj.get("moderate_status") or "").strip(),
                "visibility": item.get("visibility_details") if isinstance(item.get("visibility_details"), dict) else {},
                "fetched_at": _now_iso(),
                "item": item,
            }
            found_items.append(item)

    skus = [int(x) for x in sku_to_offer.keys() if str(x).isdigit()]
    for start in range(0, len(skus), 100):
        chunk = skus[start:start + 100]
        body = await _post_api_key("/v1/product/rating-by-sku", {"skus": chunk}, api_key, client_id)
        rows = body.get("products") if isinstance(body, dict) else []
        if not isinstance(rows, list):
            rows = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sku = str(row.get("sku") or "").strip()
            offer_id = sku_to_offer.get(sku)
            if not offer_id:
                continue
            product = offer_to_product.get(offer_id)
            pid = str(product.get("id") or "").strip() if isinstance(product, dict) else ""
            rating_items[f"{store_id}:{offer_id}"] = {
                "store_id": store_id,
                "store_title": store_title,
                "client_id": client_id,
                "offer_id": offer_id,
                "product_id": pid or None,
                "sku": sku,
                "rating": row.get("rating"),
                "groups": row.get("groups") if isinstance(row.get("groups"), list) else [],
                "fetched_at": _now_iso(),
                "row": row,
            }

    _save_doc(IMPORT_INFO_PATH, {"items": info_items})
    _save_doc(PRODUCT_RATING_PATH, {"items": rating_items})
    return {
        "ok": True,
        "count": len(found_items),
        "matched_products": len(selected),
        "store_id": store_id,
        "store_title": store_title,
        "items": [
            {
                "offer_id": str(item.get("offer_id") or "").strip(),
                "sku": item.get("sku"),
                "status": str(((item.get("statuses") or {}) if isinstance(item.get("statuses"), dict) else {}).get("status_name") or ""),
            }
            for item in found_items
        ],
    }
