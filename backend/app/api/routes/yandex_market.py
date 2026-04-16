from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.json_store import read_doc, write_doc
from app.core.value_mapping import provider_export_value, provider_import_value
from app.storage.relational_pim_store import load_attribute_mapping_doc, load_catalog_nodes, load_category_mappings

router = APIRouter(prefix="/marketplaces/yandex", tags=["marketplaces-yandex"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data" / "marketplaces" / "yandex_market"
ENV_PATH = BASE_DIR / ".env"

CATEGORIES_TREE_PATH = DATA_DIR / "categories_tree.json"
CATEGORY_PARAMS_PATH = DATA_DIR / "category_parameters.json"
OFFER_CARDS_PATH = DATA_DIR / "offer_cards_content.json"
OFFER_MAPPINGS_PATH = DATA_DIR / "offer_mappings_content.json"
MARKETPLACES_DIR = BASE_DIR / "data" / "marketplaces"
CATEGORY_MAPPING_PATH = MARKETPLACES_DIR / "category_mapping.json"
ATTR_MAPPING_PATH = MARKETPLACES_DIR / "attribute_master_mapping.json"
ATTR_VALUES_DICT_PATH = MARKETPLACES_DIR / "attribute_value_dictionary.json"
CONNECTORS_STATE_PATH = MARKETPLACES_DIR / "connectors_scheduler.json"
PRODUCTS_PATH = BASE_DIR / "data" / "products.json"
CATALOG_NODES_PATH = BASE_DIR / "data" / "catalog_nodes.json"
PRODUCT_GROUPS_PATH = BASE_DIR / "data" / "product_groups.json"

YANDEX_API_BASE = "https://api.partner.market.yandex.ru"
YANDEX_DISK_API_BASE = "https://cloud-api.yandex.net/v1/disk/public/resources/download"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_token() -> str:
    return (
        os.getenv("YANDEX_MARKET_API_TOKEN", "").strip()
        or os.getenv("YANDEX_MARKET_TOKEN", "").strip()
        or _env_file_value("YANDEX_MARKET_API_TOKEN")
        or _env_file_value("YANDEX_MARKET_TOKEN")
    )


def _env_auth_mode() -> str:
    return (
        os.getenv("YANDEX_MARKET_AUTH_MODE", "").strip().lower()
        or _env_file_value("YANDEX_MARKET_AUTH_MODE").lower()
        or "auto"
    )


def _env_business_id() -> str:
    return (
        os.getenv("YANDEX_MARKET_BUSINESS_ID", "").strip()
        or os.getenv("YANDEX_BUSINESS_ID", "").strip()
        or _env_file_value("YANDEX_MARKET_BUSINESS_ID")
        or _env_file_value("YANDEX_BUSINESS_ID")
    )


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


def _auth_headers(token: str, mode: str) -> Dict[str, str]:
    mode = (mode or "api-key").strip().lower()
    if mode == "oauth":
        return {"Authorization": f"OAuth {token}"}
    if mode == "bearer":
        return {"Authorization": f"Bearer {token}"}
    return {"Api-Key": token}


def _guess_auth_modes(token: str, requested_mode: str = "auto") -> List[str]:
    raw = str(token or "").strip()
    requested = str(requested_mode or "").strip().lower() or "auto"
    if requested not in {"auto", "api-key", "oauth", "bearer"}:
        requested = "auto"

    if not raw:
        return ["api-key"]

    # Yandex Market Api-Key examples use ACMA:* tokens and must go in Api-Key header.
    if raw.startswith("ACMA:"):
        preferred = ["api-key"]
        fallbacks = []
    # OAuth tokens usually start with y0_ and go through Authorization header.
    elif raw.startswith("y0_"):
        preferred = ["bearer", "oauth"]
        fallbacks = []
    else:
        preferred = ["api-key", "bearer", "oauth"]
        fallbacks = []

    if requested == "auto":
        return preferred + [x for x in fallbacks if x not in preferred]
    if requested in preferred:
        return [requested] + [x for x in preferred if x != requested] + [x for x in fallbacks if x != requested and x not in preferred]
    # Explicit mode conflicts with token shape: keep requested as fallback, but try the compatible mode first.
    return preferred + ([requested] if requested not in preferred else []) + [x for x in fallbacks if x != requested and x not in preferred]


def _to_str_id(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _extract_parameters(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = body.get("result") if isinstance(body, dict) else {}
    params = result.get("parameters") if isinstance(result, dict) else []
    return [p for p in (params or []) if isinstance(p, dict)] if isinstance(params, list) else []


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _is_public_web_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_yandex_disk_public_url(url: str) -> bool:
    host = urlparse(str(url or "").strip()).netloc.lower()
    return host.endswith("disk.yandex.ru") or host.endswith("yadi.sk")


async def _resolve_yandex_disk_download_url(public_url: str) -> str:
    if not _is_yandex_disk_public_url(public_url):
        return ""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(
                YANDEX_DISK_API_BASE,
                params={"public_key": public_url},
                headers={"Accept": "application/json"},
            )
        if resp.status_code >= 400:
            return ""
        body = resp.json() if resp.headers.get("content-type", "").lower().startswith("application/json") else {}
        href = str((body or {}).get("href") or "").strip()
        return href if _is_public_web_url(href) else ""
    except Exception:
        return ""


def _load_products() -> List[Dict[str, Any]]:
    doc = read_doc(PRODUCTS_PATH, default={"items": []})
    items = doc.get("items") if isinstance(doc, dict) else []
    return items if isinstance(items, list) else []


def _load_group_name_by_id() -> Dict[str, str]:
    doc = read_doc(PRODUCT_GROUPS_PATH, default={"items": []})
    items = doc.get("items") if isinstance(doc, dict) else []
    if not isinstance(items, list):
        return {}
    out: Dict[str, str] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        gid = str(row.get("id") or "").strip()
        name = str(row.get("name") or "").strip()
        if gid and name:
            out[gid] = name
    return out


def _product_group_name(product: Dict[str, Any], group_name_by_id: Optional[Dict[str, str]] = None) -> str:
    gid = str(product.get("group_id") or "").strip()
    if not gid:
        return ""
    mapping = group_name_by_id or _load_group_name_by_id()
    return str(mapping.get(gid) or "").strip()


def _save_products(items: List[Dict[str, Any]]) -> None:
    write_doc(PRODUCTS_PATH, {"version": 1, "items": items})


def _load_nodes() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _parent_map(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for n in nodes:
        nid = str(n.get("id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        if nid and pid:
            out[nid] = pid
    return out


def _load_category_mapping() -> Dict[str, Dict[str, str]]:
    items = load_category_mappings()
    out: Dict[str, Dict[str, str]] = {}
    for cid, row in (items or {}).items():
        if not isinstance(row, dict):
            continue
        out[str(cid)] = {str(k): str(v) for k, v in row.items() if str(v or "").strip()}
    return out


def _effective_yandex_category_id(category_id: str, mappings: Dict[str, Dict[str, str]], parent_by_id: Dict[str, str]) -> str:
    cur = str(category_id or "").strip()
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = mappings.get(cur) or {}
        yid = str(row.get("yandex_market") or "").strip()
        if yid:
            return yid
        cur = parent_by_id.get(cur, "")
    return ""


def _load_attr_mapping_rows() -> Dict[str, List[Dict[str, Any]]]:
    doc = load_attribute_mapping_doc()
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for cid, row in items.items():
        if not isinstance(row, dict):
            continue
        rows = row.get("rows")
        if isinstance(rows, list) and rows:
            out[str(cid)] = [x for x in rows if isinstance(x, dict)]
    return out


def _load_attr_value_refs() -> Dict[str, Dict[str, Any]]:
    doc = read_doc(ATTR_VALUES_DICT_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for cid, row in items.items():
        if isinstance(row, dict):
            out[str(cid)] = row
    return out


def _yandex_offer_id_source() -> str:
    return "sku_gt"


def _default_import_business_id() -> str:
    doc = read_doc(CONNECTORS_STATE_PATH, default={})
    providers = doc.get("providers") if isinstance(doc, dict) else {}
    prow = providers.get("yandex_market") if isinstance(providers, dict) else {}
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    if isinstance(stores, list):
        for store in stores:
            if not isinstance(store, dict):
                continue
            if not bool(store.get("enabled")):
                continue
            business_id = str(store.get("business_id") or "").strip()
            if business_id:
                return business_id
    return ""


def _default_import_store_credentials() -> Dict[str, str]:
    doc = read_doc(CONNECTORS_STATE_PATH, default={})
    providers = doc.get("providers") if isinstance(doc, dict) else {}
    prow = providers.get("yandex_market") if isinstance(providers, dict) else {}
    stores = prow.get("import_stores") if isinstance(prow, dict) else []
    if isinstance(stores, list):
        for store in stores:
            if not isinstance(store, dict):
                continue
            if not bool(store.get("enabled")):
                continue
            business_id = str(store.get("business_id") or "").strip()
            if not business_id:
                continue
            auth_mode = str(store.get("auth_mode") or "").strip().lower() or "auto"
            if auth_mode not in {"auto", "api-key", "oauth", "bearer"}:
                auth_mode = "auto"
            return {
                "business_id": business_id,
                "token": str(store.get("token") or "").strip(),
                "auth_mode": auth_mode,
            }
    return {"business_id": "", "token": "", "auth_mode": "auto"}


async def probe_store_access(*, token: str, business_id: str, auth_mode: str = "auto") -> Dict[str, Any]:
    token = str(token or "").strip()
    business_id = str(business_id or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_API_TOKEN_MISSING")
    if not business_id:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_BUSINESS_ID_MISSING")

    auth_mode = str(auth_mode or "").strip().lower() or "auto"
    modes = _guess_auth_modes(token, auth_mode)
    last_error = ""
    for mode in modes:
        headers = {
            **_auth_headers(token, mode),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                res = await client.post(
                    f"{YANDEX_API_BASE}/v2/businesses/{business_id}/offer-cards",
                    params={"limit": 1},
                    json={"offerIds": [], "withRecommendations": False},
                    headers=headers,
                )
            body = res.json() if res.content else {}
            if res.is_success:
                return {
                    "ok": True,
                    "auth_mode": mode,
                    "business_id": business_id,
                    "details": body.get("result") if isinstance(body, dict) else {},
                }
            if (
                res.status_code == 400
                and isinstance(body, dict)
                and any(
                    str(err.get("code") or "").strip() == "BAD_REQUEST"
                    and "offerids size must be between 1 and 200" in str(err.get("message") or "").strip().lower()
                    for err in (body.get("errors") or [])
                    if isinstance(err, dict)
                )
            ):
                return {
                    "ok": True,
                    "auth_mode": mode,
                    "business_id": business_id,
                    "details": {"probe": "authorized", "validation": "offerIds-required"},
                }
            last_error = f"[{mode}] {res.status_code}: {res.text[:400]}"
        except HTTPException:
            raise
        except Exception as e:
            last_error = f"[{mode}] {e}"
    raise HTTPException(status_code=502, detail=f"YANDEX_HTTP_FAILED {last_error}")


def _effective_attr_rows(category_id: str, rows_by_cid: Dict[str, List[Dict[str, Any]]], parent_by_id: Dict[str, str]) -> List[Dict[str, Any]]:
    cur = str(category_id or "").strip()
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        rows = rows_by_cid.get(cur) or []
        if rows:
            return rows
        cur = parent_by_id.get(cur, "")
    return []


def _effective_attr_value_ref(category_id: str, refs_by_cid: Dict[str, Dict[str, Any]], parent_by_id: Dict[str, str]) -> Dict[str, Any]:
    cur = str(category_id or "").strip()
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = refs_by_cid.get(cur)
        if isinstance(row, dict):
            return row
        cur = parent_by_id.get(cur, "")
    return {}


@router.get("/media-proxy")
async def yandex_media_proxy(url: str = Query(..., min_length=8)) -> Response:
    original_url = str(url or "").strip()
    if not _is_public_web_url(original_url):
        raise HTTPException(status_code=400, detail="INVALID_MEDIA_URL")

    resolved_url = await _resolve_yandex_disk_download_url(original_url)
    target_url = resolved_url or original_url
    try:
        async with httpx.AsyncClient(
            timeout=40.0,
            follow_redirects=True,
            headers={
                "User-Agent": "GlobalPIM/1.0",
                "Accept": "image/avif,image/webp,image/apng,image/*,video/*,*/*;q=0.8",
            },
        ) as client:
            resp = await client.get(target_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"YANDEX_MEDIA_FETCH_FAILED:{exc}") from exc

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"YANDEX_MEDIA_FETCH_FAILED:{resp.status_code}")

    content_type = str(resp.headers.get("content-type") or "application/octet-stream").strip()
    if content_type.lower().startswith("text/html"):
        raise HTTPException(status_code=502, detail="YANDEX_MEDIA_NOT_BINARY")

    headers: Dict[str, str] = {"Cache-Control": "public, max-age=3600"}
    for key in ("etag", "last-modified", "content-length"):
        value = str(resp.headers.get(key) or "").strip()
        if value:
            headers[key] = value
    return Response(content=resp.content, media_type=content_type.split(";", 1)[0], headers=headers)


def _extract_feature_value(product: Dict[str, Any], *, code: str = "", name: str = "") -> str:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    feats = content.get("features") if isinstance(content.get("features"), list) else []
    for f in feats:
        if not isinstance(f, dict):
            continue
        fcode = _norm(f.get("code"))
        fname = _norm(f.get("name"))
        if code and fcode == _norm(code):
            return str(f.get("value") or "").strip()
        if name and fname == _norm(name):
            return str(f.get("value") or "").strip()
    return ""


def _parameter_value_text(param: Dict[str, Any]) -> str:
    if not isinstance(param, dict):
        return ""
    direct = str(param.get("value") or "").strip()
    if direct:
        return direct
    values = param.get("values")
    if isinstance(values, list):
        parts: List[str] = []
        for item in values:
            if isinstance(item, dict):
                text = str(item.get("value") or item.get("name") or item.get("title") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                parts.append(text)
        if parts:
            return ", ".join(parts)
    return ""


def _resolved_provider_value(raw_value: str, canonical_value: str) -> str:
    return str(canonical_value or "").strip() or str(raw_value or "").strip()


def _normalize_feature_sources(feature: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for provider, payload in source_values.items():
        if not isinstance(payload, dict):
            continue
        normalized[str(provider)] = {str(k): v for k, v in payload.items() if isinstance(v, dict)}
    return normalized


_DEPRECATED_FEATURE_ALIASES: Dict[str, Tuple[str, str]] = {
    "артикул": ("part_number", "Партномер"),
    "весг": ("package_weight", "Вес упаковки, г"),
    "длинамм": ("package_length", "Длина упаковки, мм"),
    "ширинамм": ("package_width", "Ширина упаковки, мм"),
    "высотамм": ("package_height", "Высота упаковки, мм"),
    "название_группы_вариантов": ("group_id", "Группа товара"),
    "изображение_для_миниатюры": ("media_images", "Картинки"),
}


def _canonical_feature_identity(code: Any, name: Any) -> Tuple[str, str]:
    raw_code = str(code or "").strip()
    raw_name = str(name or "").strip()
    alias = _DEPRECATED_FEATURE_ALIASES.get(_norm(raw_code)) or _DEPRECATED_FEATURE_ALIASES.get(_norm(raw_name))
    if alias:
        return alias
    return raw_code, raw_name


def _dedupe_yandex_sources(items: Dict[str, Any]) -> Dict[str, Any]:
    by_business: Dict[str, Dict[str, Any]] = {}
    for source_key, payload in items.items():
        if not isinstance(payload, dict):
            continue
        business_id = str(payload.get("business_id") or "").strip()
        store_id = str(payload.get("store_id") or source_key or "").strip()
        store_title = str(payload.get("store_title") or store_id or "").strip()
        candidate = {
            "store_id": store_id,
            "store_title": store_title,
            "business_id": business_id,
            "raw_value": str(payload.get("raw_value") or "").strip(),
            "canonical_value": str(payload.get("canonical_value") or "").strip(),
            "resolved_value": str(payload.get("resolved_value") or "").strip(),
            "updated_at": str(payload.get("updated_at") or _now_iso()),
        }
        key = business_id or store_id or source_key
        current = by_business.get(key)
        if not current:
            by_business[key] = candidate
            continue
        current_sid = str(current.get("store_id") or "").strip()
        candidate_sid = str(candidate.get("store_id") or "").strip()
        current_is_legacy = current_sid.isdigit()
        candidate_is_legacy = candidate_sid.isdigit()
        if current_is_legacy and not candidate_is_legacy:
            by_business[key] = candidate
            continue
        if current_is_legacy == candidate_is_legacy:
            current_updated = str(current.get("updated_at") or "")
            candidate_updated = str(candidate.get("updated_at") or "")
            if candidate_updated >= current_updated:
                by_business[key] = candidate
    return {
        str((payload.get("store_id") or business_id or "")).strip() or str(business_id): payload
        for business_id, payload in by_business.items()
        if isinstance(payload, dict)
    }


def _cleanup_product_features(features: Any) -> List[Dict[str, Any]]:
    if not isinstance(features, list):
        return []
    merged: List[Dict[str, Any]] = []
    by_code: Dict[str, int] = {}
    for item in features:
        if not isinstance(item, dict):
            continue
        code, name = _canonical_feature_identity(item.get("code"), item.get("name"))
        code = str(code or "").strip()
        name = str(name or code).strip()
        if not code and not name:
            continue
        feature = dict(item)
        feature["code"] = code
        feature["name"] = name
        source_values = _normalize_feature_sources(feature)
        ym_sources = source_values.get("yandex_market")
        if isinstance(ym_sources, dict):
            source_values["yandex_market"] = _dedupe_yandex_sources(ym_sources)
        if source_values:
            feature["source_values"] = source_values
        value = str(feature.get("value") or "").strip()
        key = code or _norm(name)
        existing_idx = by_code.get(key)
        if existing_idx is None:
            merged.append(feature)
            by_code[key] = len(merged) - 1
            continue
        current = merged[existing_idx]
        current_value = str(current.get("value") or "").strip()
        if not current_value and value:
            current["value"] = value
        if not current.get("selected") and feature.get("selected"):
            current["selected"] = feature.get("selected")
        cur_sources = _normalize_feature_sources(current)
        new_sources = _normalize_feature_sources(feature)
        for provider, payload in new_sources.items():
            provider_sources = dict(cur_sources.get(provider) or {})
            provider_sources.update(payload if isinstance(payload, dict) else {})
            if provider == "yandex_market":
                provider_sources = _dedupe_yandex_sources(provider_sources)
            cur_sources[provider] = provider_sources
        if cur_sources:
            current["source_values"] = cur_sources
        conflict = feature.get("conflict")
        if isinstance(conflict, dict) and conflict.get("active") and not (current.get("conflict") or {}).get("active"):
            current["conflict"] = conflict
    return merged


def _merge_yandex_feature_value(
    current: Optional[Dict[str, Any]],
    *,
    code: str,
    catalog_name: str,
    raw_value: str,
    canonical_value: str,
    store_key: str,
    store_id: str,
    store_title: str,
    business_id: str,
    overwrite_existing: bool,
) -> Dict[str, Any]:
    base = dict(current or {})
    sources = _normalize_feature_sources(base)
    ym_sources = _dedupe_yandex_sources(dict(sources.get("yandex_market") or {}))
    ym_sources[store_key] = {
        "store_id": store_id or store_key,
        "store_title": store_title or store_key,
        "business_id": business_id,
        "raw_value": str(raw_value or "").strip(),
        "canonical_value": str(canonical_value or "").strip(),
        "resolved_value": _resolved_provider_value(raw_value, canonical_value),
        "updated_at": _now_iso(),
    }
    ym_sources = _dedupe_yandex_sources(ym_sources)
    sources["yandex_market"] = ym_sources

    variants: List[Dict[str, Any]] = []
    unique_values: Dict[str, str] = {}
    for source in ym_sources.values():
        if not isinstance(source, dict):
            continue
        resolved = str(source.get("resolved_value") or "").strip()
        if not resolved:
            continue
        variants.append(
            {
                "store_id": str(source.get("store_id") or "").strip(),
                "store_title": str(source.get("store_title") or "").strip(),
                "business_id": str(source.get("business_id") or "").strip(),
                "value": resolved,
                "raw_value": str(source.get("raw_value") or "").strip(),
                "canonical_value": str(source.get("canonical_value") or "").strip(),
            }
        )
        norm_key = _norm(resolved)
        if norm_key and norm_key not in unique_values:
            unique_values[norm_key] = resolved

    current_value = str(base.get("value") or "").strip()
    selected = str(base.get("selected") or "custom").strip() or "custom"
    conflict_active = len(unique_values) > 1
    unified_value = next(iter(unique_values.values()), "")

    next_feature = {
        "code": code,
        "name": catalog_name,
        "restore": str(base.get("restore") or ""),
        "store77": str(base.get("store77") or ""),
        "selected": selected,
        "value": current_value,
        "source_values": sources,
    }

    if not conflict_active:
        if unified_value and (overwrite_existing or not current_value or selected == "yandex_market"):
            next_feature["value"] = unified_value
            next_feature["selected"] = "yandex_market"
    elif not current_value and unified_value:
        next_feature["value"] = unified_value

    next_feature["conflict"] = {
        "provider": "yandex_market",
        "active": conflict_active,
        "variants": variants,
    }
    return next_feature


def _load_offer_cards_doc() -> Dict[str, Any]:
    doc = read_doc(OFFER_CARDS_PATH, default={"version": 1, "items": {}, "updated_at": None})
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}, "updated_at": None}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    return doc


def _save_offer_cards_doc(doc: Dict[str, Any]) -> None:
    doc["updated_at"] = _now_iso()
    write_doc(OFFER_CARDS_PATH, doc)


def _load_offer_mappings_doc() -> Dict[str, Any]:
    doc = read_doc(OFFER_MAPPINGS_PATH, default={"version": 1, "items": {}, "updated_at": None})
    if not isinstance(doc, dict):
        doc = {"version": 1, "items": {}, "updated_at": None}
    if not isinstance(doc.get("items"), dict):
        doc["items"] = {}
    return doc


def _save_offer_mappings_doc(doc: Dict[str, Any]) -> None:
    doc["updated_at"] = _now_iso()
    write_doc(OFFER_MAPPINGS_PATH, doc)


def _extract_offer_mapping_entries(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = body.get("result") if isinstance(body, dict) else {}
    if isinstance(result, list):
        return [x for x in result if isinstance(x, dict)]
    if not isinstance(result, dict):
        return []
    for key in ("offerMappings", "offerMappingEntries", "items", "offers"):
        arr = result.get(key)
        if isinstance(arr, list):
            return [x for x in arr if isinstance(x, dict)]
    return []


def _entry_offer_id(entry: Dict[str, Any]) -> str:
    for container in (
        entry,
        entry.get("offer") if isinstance(entry.get("offer"), dict) else None,
        entry.get("mapping") if isinstance(entry.get("mapping"), dict) else None,
    ):
        if not isinstance(container, dict):
            continue
        for key in ("offerId", "shopSku"):
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return ""


def _entry_text(entry: Dict[str, Any], *keys: str) -> str:
    for container in (
        entry,
        entry.get("offer") if isinstance(entry.get("offer"), dict) else None,
        entry.get("mapping") if isinstance(entry.get("mapping"), dict) else None,
    ):
        if not isinstance(container, dict):
            continue
        for key in keys:
            value = str(container.get(key) or "").strip()
            if value:
                return value
    return ""


def _entry_urls(entry: Dict[str, Any], *keys: str) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for container in (
        entry,
        entry.get("offer") if isinstance(entry.get("offer"), dict) else None,
        entry.get("mapping") if isinstance(entry.get("mapping"), dict) else None,
    ):
        if not isinstance(container, dict):
            continue
        for key in keys:
            payload = container.get(key)
            if not isinstance(payload, list):
                continue
            for item in payload:
                if isinstance(item, dict):
                    url = str(item.get("url") or item.get("link") or item.get("value") or "").strip()
                else:
                    url = str(item or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                out.append(url)
    return out


def _filter_importable_media_urls(urls: List[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for raw in urls or []:
        url = str(raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        if _is_yandex_disk_public_url(url):
            continue
        out.append(url)
    return out


def _entry_values(entry: Dict[str, Any], *keys: str) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for container in (
        entry,
        entry.get("offer") if isinstance(entry.get("offer"), dict) else None,
        entry.get("mapping") if isinstance(entry.get("mapping"), dict) else None,
    ):
        if not isinstance(container, dict):
            continue
        for key in keys:
            payload = container.get(key)
            if isinstance(payload, list):
                items = payload
            elif payload is None:
                items = []
            else:
                items = [payload]
            for item in items:
                if isinstance(item, dict):
                    value = str(item.get("value") or item.get("name") or item.get("title") or item.get("code") or "").strip()
                else:
                    value = str(item or "").strip()
                if not value or value in seen:
                    continue
                seen.add(value)
                out.append(value)
    return out


def _merge_media_items(existing: Any, urls: List[str], overwrite_existing: bool) -> List[Dict[str, str]]:
    fresh = [{"url": str(url).strip()} for url in urls if str(url).strip()]
    if overwrite_existing:
        return fresh
    current = existing if isinstance(existing, list) else []
    out: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for item in current:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    for item in fresh:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def _upsert_imported_system_feature(
    *,
    features: List[Dict[str, Any]],
    feature_by_code: Dict[str, Dict[str, Any]],
    row: Optional[Dict[str, Any]],
    raw_value: str,
    store_key: str,
    store_id: str,
    store_title: str,
    business_id: str,
    overwrite_existing: bool,
) -> bool:
    if not isinstance(row, dict):
        return False
    catalog_name = str(row.get("catalog_name") or "").strip()
    if not catalog_name or not str(raw_value or "").strip():
        return False
    code = str(row.get("code") or "").strip()
    if not code:
        from app.storage.json_store import slugify_code as _slugify_code

        code = _slugify_code(catalog_name)
    current = feature_by_code.get(code)
    next_feature = _merge_yandex_feature_value(
        current,
        code=code,
        catalog_name=catalog_name,
        raw_value=raw_value,
        canonical_value=raw_value,
        store_key=store_key,
        store_id=store_id,
        store_title=store_title,
        business_id=business_id,
        overwrite_existing=overwrite_existing,
    )
    if current:
        idx = next((i for i, f in enumerate(features) if isinstance(f, dict) and str(f.get("code") or "").strip() == code), -1)
        if idx >= 0 and features[idx] != next_feature:
            features[idx] = next_feature
            feature_by_code[code] = next_feature
            return True
        return False
    features.append(next_feature)
    feature_by_code[code] = next_feature
    return True


async def _fetch_offer_mappings_once(
    *,
    token: str,
    business_id: str,
    offer_ids: List[str],
    language: str,
    modes: List[str],
) -> Dict[str, Any]:
    last_error = ""
    last_body: Dict[str, Any] = {}
    for mode in modes:
        headers = {
            **_auth_headers(token, mode),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{YANDEX_API_BASE}/v2/businesses/{business_id}/offer-mappings",
                params={"language": (language or "RU").strip().upper()},
                json={"offerIds": offer_ids},
                headers=headers,
            )
        body = res.json() if res.content else {}
        if isinstance(body, dict):
            last_body = body
        if res.is_success:
            return {"ok": True, "body": body, "error": ""}
        last_error = f"[{mode}] {res.status_code}: {res.text[:400]}"
    return {"ok": False, "body": last_body, "error": last_error}


def _extract_product_value(product: Dict[str, Any], catalog_name: str) -> str:
    n = _norm(catalog_name)
    if n in {"sku gt", "gt id", "sku_gt"}:
        return str(product.get("sku_gt") or "").strip()
    if n in {"sku pim", "pim id", "sku_pim"}:
        return str(product.get("sku_pim") or "").strip()
    if n in {"наименование товара", "name", "title"}:
        return str(product.get("title") or "").strip()
    if n in {"описание товара", "описание", "description", "аннотация"}:
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        return str(content.get("description") or "").strip()
    if n in {"тип товара", "product_type"}:
        return str(product.get("type") or "").strip()
    if "бренд" in n or n == "brand":
        v = _extract_feature_value(product, code="brand", name="Бренд")
        return v
    if "линейка" in n or n == "line":
        v = _extract_feature_value(product, code="line", name="Линейка")
        return v
    if "штрихкод" in n or n == "barcode":
        v = _extract_feature_value(product, code="barcode", name="Штрихкод")
        return v
    if "группа товара" in n or n == "group_id":
        return _product_group_name(product)
    if "срок службы" in n or n == "service_life":
        v = _extract_feature_value(product, code="service_life", name="Срок службы")
        return v
    if "страна производства" in n or "страна происхождения" in n or n == "country_of_origin":
        v = _extract_feature_value(product, code="country_of_origin", name="Страна производства")
        return v
    if "гарантийный срок" in n or "срок гарантии" in n or n == "warranty_period":
        v = _extract_feature_value(product, code="warranty_period", name="Гарантийный срок")
        return v
    if n in {"ширина упаковки", "ширина упаковки, мм", "package_width"}:
        return _extract_feature_value(product, code="package_width", name="Ширина упаковки")
    if n in {"длина упаковки", "длина упаковки, мм", "глубина упаковки", "глубина упаковки, мм", "длина", "длина, мм", "глубина", "глубина, мм", "package_length"}:
        return _extract_feature_value(product, code="package_length", name="Длина упаковки")
    if n in {"высота упаковки", "высота упаковки, мм", "package_height"}:
        return _extract_feature_value(product, code="package_height", name="Высота упаковки")
    if n in {"вес", "вес, г", "вес упаковки", "вес упаковки, г", "вес брутто", "вес брутто, г", "package_weight"}:
        return _extract_feature_value(product, code="package_weight", name="Вес упаковки")
    if n in {"вес устройства", "вес устройства, г", "вес нетто", "вес нетто, г", "device_weight"}:
        return _extract_feature_value(product, code="device_weight", name="Вес устройства")
    if n in {"ширина устройства", "ширина устройства, мм", "device_width"}:
        return _extract_feature_value(product, code="device_width", name="Ширина устройства")
    if n in {"длина устройства", "длина устройства, мм", "длина товара", "длина корпуса", "глубина устройства", "глубина устройства, мм", "глубина товара", "глубина товара, мм", "глубина корпуса", "глубина корпуса, мм", "device_length"}:
        return _extract_feature_value(product, code="device_length", name="Длина устройства")
    if n in {"высота устройства", "высота устройства, мм", "device_height"}:
        return _extract_feature_value(product, code="device_height", name="Высота устройства")
    # fallback to features by exact name
    return _extract_feature_value(product, name=catalog_name)


def _preferred_offer_id(product: Dict[str, Any]) -> str:
    return str(product.get("sku_gt") or "").strip()


def _dict_id_for_catalog_param(
    category_id: str,
    catalog_name: str,
    refs_by_cid: Dict[str, Dict[str, Any]],
    parent_by_id: Dict[str, str],
) -> str:
    ref = _effective_attr_value_ref(category_id, refs_by_cid, parent_by_id)
    params = ref.get("catalog_params") if isinstance(ref.get("catalog_params"), dict) else {}
    if not isinstance(params, dict):
        return ""
    target = _norm(catalog_name)
    for payload in params.values():
        if not isinstance(payload, dict):
            continue
        if _norm(payload.get("catalog_name")) != target:
            continue
        return str(payload.get("dict_id") or "").strip()
    return ""


def _find_system_row(rows: List[Dict[str, Any]], key_names: Set[str]) -> Optional[Dict[str, Any]]:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        cname = _norm(row.get("catalog_name"))
        if cname in key_names:
            return row
    return None


def _find_provider_system_row(rows: List[Dict[str, Any]], provider_code: str, target_ids: Set[str]) -> Optional[Dict[str, Any]]:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        prow = pmap.get(provider_code) if isinstance(pmap.get(provider_code), dict) else {}
        pid = _norm(prow.get("id"))
        if pid and pid in {_norm(x) for x in target_ids}:
            return row
    return None


def _is_provider_row_enabled(row: Optional[Dict[str, Any]], provider_code: str) -> bool:
    if not isinstance(row, dict):
        return False
    pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    prow = pmap.get(provider_code) if isinstance(pmap.get(provider_code), dict) else {}
    return bool(prow.get("export"))


def _yandex_required_param_ids(category_id: str) -> Set[str]:
    doc = read_doc(CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        return set()
    row = items.get(str(category_id))
    if not isinstance(row, dict):
        return set()
    raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
    params = _extract_parameters(raw)
    out: Set[str] = set()
    for p in params:
        if not isinstance(p, dict):
            continue
        if not bool(p.get("required")):
            continue
        pid = _to_str_id(p.get("id"))
        if pid:
            out.add(pid)
    return out


def _is_invalid_category_response(status_code: int, body: Dict[str, Any]) -> bool:
    if status_code != 400 or not isinstance(body, dict):
        return False
    errors = body.get("errors")
    if not isinstance(errors, list):
        return False
    for e in errors:
        if not isinstance(e, dict):
            continue
        if str(e.get("code") or "").strip().upper() == "INVALID_CATEGORY":
            return True
    return False


def _leaf_descendants_from_cached_tree(category_id: str) -> List[str]:
    category_id = _to_str_id(category_id)
    if not category_id:
        return []
    doc = read_doc(CATEGORIES_TREE_PATH, default={})
    flat = doc.get("flat") if isinstance(doc, dict) else []
    if not isinstance(flat, list):
        return []

    by_id: Dict[str, Dict[str, Any]] = {}
    children_by_parent: Dict[str, List[str]] = {}
    for row in flat:
        if not isinstance(row, dict):
            continue
        rid = _to_str_id(row.get("id"))
        if not rid:
            continue
        by_id[rid] = row
        pid = _to_str_id(row.get("parent_id"))
        children_by_parent.setdefault(pid, [])
        children_by_parent[pid].append(rid)

    if category_id not in by_id:
        return []

    # If already leaf, return itself.
    if bool(by_id[category_id].get("is_leaf")):
        return [category_id]

    out: List[str] = []
    stack = list(children_by_parent.get(category_id, []))
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        node = by_id.get(cur) or {}
        children = children_by_parent.get(cur, [])
        is_leaf = bool(node.get("is_leaf")) or len(children) == 0
        if is_leaf:
            out.append(cur)
        else:
            stack.extend(children)
    out = sorted(set(out), key=lambda x: int(x) if x.isdigit() else x)
    return out


def _merge_parameters_bodies(bodies: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for body in bodies:
        for p in _extract_parameters(body):
            pid = _to_str_id(p.get("id"))
            pname = str(p.get("name") or "").strip().lower()
            key = pid or f"name:{pname}"
            if not key:
                continue
            if key not in merged:
                merged[key] = p
                order.append(key)
    return [merged[k] for k in order], len(order)


async def _fetch_category_parameters_once(
    *,
    token: str,
    category_id: str,
    language: str,
    modes: List[str],
) -> Dict[str, Any]:
    last_error = ""
    last_body: Dict[str, Any] = {}
    invalid_category = False
    res = None
    for mode in modes:
        headers = {
            **_auth_headers(token, mode),
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"{YANDEX_API_BASE}/v2/category/{category_id}/parameters",
                params={"language": language},
                headers=headers,
            )
        body = res.json() if res.content else {}
        if isinstance(body, dict):
            last_body = body
        if res.is_success:
            return {"ok": True, "body": body, "error": "", "invalid_category": False}
        if _is_invalid_category_response(res.status_code, body if isinstance(body, dict) else {}):
            invalid_category = True
        last_error = f"[{mode}] {res.status_code}: {res.text[:400]}"
    return {"ok": False, "body": last_body, "error": last_error, "invalid_category": invalid_category}


def _normalize_tree_nodes(tree_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    roots = tree_result.get("children") if isinstance(tree_result, dict) else None
    if not isinstance(roots, list):
        roots = tree_result.get("categories") if isinstance(tree_result, dict) else None
    if not isinstance(roots, list):
        roots = []

    out: List[Dict[str, Any]] = []

    def walk(node: Dict[str, Any], parent_id: Optional[str], depth: int, path: List[str]) -> None:
        if not isinstance(node, dict):
            return

        nid = _to_str_id(node.get("id"))
        name = str(node.get("name") or node.get("title") or "").strip()
        if not nid:
            return

        cur_path = [*path, name or nid]
        children = node.get("children") if isinstance(node.get("children"), list) else []

        out.append(
            {
                "id": nid,
                "name": name,
                "parent_id": parent_id,
                "depth": depth,
                "path": " / ".join([x for x in cur_path if x]),
                "is_leaf": len(children) == 0,
            }
        )

        for child in children:
            walk(child, nid, depth + 1, cur_path)

    for root in roots:
        walk(root, None, 0, [])

    return out


class ImportCategoriesReq(BaseModel):
    language: str = Field(default="RU")
    token: Optional[str] = None
    auth_mode: Optional[str] = None


@router.post("/import/categories-tree")
async def import_categories_tree(req: ImportCategoriesReq) -> Dict[str, Any]:
    store_creds = _default_import_store_credentials()
    token = (req.token or "").strip() or str(store_creds.get("token") or "").strip() or _env_token()
    if not token:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_API_TOKEN_MISSING")

    language = (req.language or "RU").strip().upper()

    payload = {"language": language}
    auth_mode = str(req.auth_mode or "").strip().lower() or str(store_creds.get("auth_mode") or "").strip().lower() or _env_auth_mode()
    modes = _guess_auth_modes(token, auth_mode)
    last_error = ""
    try:
        res = None
        for mode in modes:
            headers = {
                **_auth_headers(token, mode),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{YANDEX_API_BASE}/v2/categories/tree",
                    json=payload,
                    headers=headers,
                )
            if res.is_success:
                break
            last_error = f"[{mode}] {res.status_code}: {res.text[:400]}"
        if not res or not res.is_success:
            raise HTTPException(status_code=502, detail=f"YANDEX_HTTP_FAILED {last_error}")

        body = res.json() if res.content else {}
        result = body.get("result") if isinstance(body, dict) else {}
        if not isinstance(result, dict):
            result = {}

        flat = _normalize_tree_nodes(result)
        doc = {
            "imported_at": _now_iso(),
            "language": language,
            "raw": body,
            "flat": flat,
            "count": len(flat),
        }
        write_doc(CATEGORIES_TREE_PATH, doc)

        return {"ok": True, "count": len(flat), "imported_at": doc["imported_at"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YANDEX_IMPORT_ERROR:{e}")


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


class ImportCategoryParamsReq(BaseModel):
    category_id: str = Field(min_length=1)
    language: str = Field(default="RU")
    token: Optional[str] = None
    auth_mode: Optional[str] = None


class OfferCardsSyncReq(BaseModel):
    category_id: Optional[str] = None
    product_ids: List[str] = Field(default_factory=list)
    include_descendants: bool = True
    with_recommendations: bool = True
    apply_to_products: bool = True
    overwrite_existing: bool = False
    limit: int = Field(default=200, ge=1, le=20000)
    token: Optional[str] = None
    auth_mode: Optional[str] = None
    business_id: Optional[str] = None
    store_id: Optional[str] = None
    store_title: Optional[str] = None
    include_offer_mappings: bool = True


class ExportPreviewReq(BaseModel):
    product_ids: List[str] = Field(default_factory=list)
    only_active: bool = True
    limit: int = Field(default=50, ge=1, le=500)


@router.post("/import/category-parameters")
async def import_category_parameters(req: ImportCategoryParamsReq) -> Dict[str, Any]:
    store_creds = _default_import_store_credentials()
    token = (req.token or "").strip() or str(store_creds.get("token") or "").strip() or _env_token()
    if not token:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_API_TOKEN_MISSING")

    category_id = _to_str_id(req.category_id)
    language = (req.language or "RU").strip().upper()

    auth_mode = str(req.auth_mode or "").strip().lower() or str(store_creds.get("auth_mode") or "").strip().lower() or _env_auth_mode()
    modes = _guess_auth_modes(token, auth_mode)
    try:
        fetched = await _fetch_category_parameters_once(
            token=token,
            category_id=category_id,
            language=language,
            modes=modes,
        )
        body = fetched.get("body") if isinstance(fetched, dict) else {}
        merged_from_leafs = False
        merged_leaf_ids: List[str] = []

        if not fetched.get("ok"):
            if fetched.get("invalid_category"):
                leaf_ids = _leaf_descendants_from_cached_tree(category_id)
                leaf_bodies: List[Dict[str, Any]] = []
                leaf_errors: List[str] = []
                for leaf_id in leaf_ids:
                    leaf_fetched = await _fetch_category_parameters_once(
                        token=token,
                        category_id=leaf_id,
                        language=language,
                        modes=modes,
                    )
                    if leaf_fetched.get("ok"):
                        leaf_body = leaf_fetched.get("body")
                        if isinstance(leaf_body, dict):
                            leaf_bodies.append(leaf_body)
                            merged_leaf_ids.append(leaf_id)
                    else:
                        leaf_errors.append(str(leaf_fetched.get("error") or ""))

                if leaf_bodies:
                    merged_params, merged_count = _merge_parameters_bodies(leaf_bodies)
                    body = {
                        "result": {
                            "parameters": merged_params,
                            "category": {"id": category_id},
                        },
                        "meta": {
                            "merged_from_leafs": True,
                            "leaf_ids": merged_leaf_ids,
                            "leafs_count": len(merged_leaf_ids),
                            "parameters_count": merged_count,
                            "leaf_errors": [e for e in leaf_errors if e][:20],
                        },
                    }
                    merged_from_leafs = True
                else:
                    last_error = str(fetched.get("error") or "INVALID_CATEGORY")
                    raise HTTPException(status_code=502, detail=f"YANDEX_HTTP_FAILED {last_error}")
            else:
                last_error = str(fetched.get("error") or "NO_RESPONSE")
                raise HTTPException(status_code=502, detail=f"YANDEX_HTTP_FAILED {last_error}")

        doc = read_doc(CATEGORY_PARAMS_PATH, default={"items": {}})
        if not isinstance(doc, dict):
            doc = {"items": {}}
        if not isinstance(doc.get("items"), dict):
            doc["items"] = {}

        doc["items"][category_id] = {
            "category_id": category_id,
            "imported_at": _now_iso(),
            "language": language,
            "raw": body,
            "merged_from_leafs": merged_from_leafs,
            "leaf_ids": merged_leaf_ids,
        }
        write_doc(CATEGORY_PARAMS_PATH, doc)

        params = _extract_parameters(body if isinstance(body, dict) else {})
        count = len(params)

        return {
            "ok": True,
            "category_id": category_id,
            "parameters_count": count,
            "merged_from_leafs": merged_from_leafs,
            "leaf_ids": merged_leaf_ids,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"YANDEX_IMPORT_ERROR:{e}")


@router.get("/category-parameters/{category_id}")
def get_category_parameters(category_id: str) -> Dict[str, Any]:
    doc = read_doc(CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}

    row = items.get(str(category_id))
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="CATEGORY_PARAMETERS_NOT_FOUND")

    return {"ok": True, "item": row}


@router.get("/category-parameters")
def list_category_parameters() -> Dict[str, Any]:
    doc = read_doc(CATEGORY_PARAMS_PATH, default={"items": {}})
    items = doc.get("items") if isinstance(doc, dict) else {}
    if not isinstance(items, dict):
        items = {}

    out: List[Dict[str, Any]] = []
    for category_id, row in items.items():
        if not isinstance(row, dict):
            continue
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        result = raw.get("result") if isinstance(raw, dict) else {}
        params = result.get("parameters") if isinstance(result, dict) else []
        out.append(
            {
                "category_id": str(category_id),
                "imported_at": row.get("imported_at"),
                "language": row.get("language"),
                "parameters_count": len(params) if isinstance(params, list) else 0,
            }
        )
    out.sort(key=lambda x: str(x.get("category_id") or ""))
    return {"ok": True, "items": out, "count": len(out)}


@router.post("/offer-cards/sync")
async def sync_offer_cards(req: OfferCardsSyncReq) -> Dict[str, Any]:
    store_creds = _default_import_store_credentials()
    token = (req.token or "").strip() or str(store_creds.get("token") or "").strip() or _env_token()
    if not token:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_API_TOKEN_MISSING")

    business_id = str(req.business_id or "").strip() or str(store_creds.get("business_id") or "").strip() or _default_import_business_id() or _env_business_id()
    if not business_id:
        raise HTTPException(status_code=400, detail="YANDEX_MARKET_BUSINESS_ID_MISSING")
    store_id = str(req.store_id or "").strip()
    store_title = str(req.store_title or "").strip()
    store_key = store_id or business_id

    products = _load_products()
    group_name_by_id = _load_group_name_by_id()
    nodes = _load_nodes()
    parent_by_id = _parent_map(nodes)
    mappings = _load_category_mapping()
    attr_rows_by_cid = _load_attr_mapping_rows()
    attr_value_refs_by_cid = _load_attr_value_refs()

    target_ids: Set[str] = {str(x or "").strip() for x in (req.product_ids or []) if str(x or "").strip()}
    if req.category_id:
        root_category_id = str(req.category_id or "").strip()
        children: Dict[str, List[str]] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            pid = str(node.get("parent_id") or "").strip()
            nid = str(node.get("id") or "").strip()
            if nid:
                children.setdefault(pid, []).append(nid)
        stack = [root_category_id]
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
    for product in products:
        if not isinstance(product, dict):
            continue
        pid = str(product.get("id") or "").strip()
        if target_ids and pid not in target_ids:
            continue
        offer_id = _preferred_offer_id(product)
        if not offer_id:
            continue
        selected.append(product)
        if len(selected) >= int(req.limit):
            break

    if not selected:
        return {
            "ok": True,
            "count": 0,
            "matched_products": 0,
            "updated_products": 0,
            "items": [],
        }

    auth_mode = str(req.auth_mode or "").strip().lower() or str(store_creds.get("auth_mode") or "").strip().lower() or _env_auth_mode()
    modes = _guess_auth_modes(token, auth_mode)
    product_by_offer_id: Dict[str, Dict[str, Any]] = {}
    for product in selected:
        offer_id = _preferred_offer_id(product)
        if offer_id:
            product_by_offer_id[offer_id] = product

    items_out: List[Dict[str, Any]] = []
    cache_doc = _load_offer_cards_doc()
    cache_items = cache_doc.get("items") if isinstance(cache_doc.get("items"), dict) else {}
    if not isinstance(cache_items, dict):
        cache_items = {}
    mappings_doc = _load_offer_mappings_doc()
    mappings_cache_items = mappings_doc.get("items") if isinstance(mappings_doc.get("items"), dict) else {}
    if not isinstance(mappings_cache_items, dict):
        mappings_cache_items = {}

    updated_products = 0
    changed_product_ids: Set[str] = set()

    if req.apply_to_products:
        for product in selected:
            if not isinstance(product, dict):
                continue
            content = product.get("content") if isinstance(product.get("content"), dict) else {}
            features = content.get("features") if isinstance(content.get("features"), list) else []
            cleaned = _cleanup_product_features(features)
            if cleaned != features:
                content["features"] = cleaned
                product["content"] = content
                product["updated_at"] = _now_iso()
                changed_product_ids.add(str(product.get("id") or "").strip())

    offer_ids = list(product_by_offer_id.keys())
    for start in range(0, len(offer_ids), 100):
        chunk = offer_ids[start:start + 100]
        last_error = ""
        response_body: Dict[str, Any] = {}
        response_ok = False
        for mode in modes:
            headers = {
                **_auth_headers(token, mode),
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{YANDEX_API_BASE}/v2/businesses/{business_id}/offer-cards",
                    params={"limit": min(100, len(chunk))},
                    json={"offerIds": chunk, "withRecommendations": bool(req.with_recommendations)},
                    headers=headers,
                )
            body = res.json() if res.content else {}
            if isinstance(body, dict):
                response_body = body
            if res.is_success:
                response_ok = True
                break
            last_error = f"[{mode}] {res.status_code}: {res.text[:400]}"
        if not response_ok:
            raise HTTPException(status_code=502, detail=f"YANDEX_HTTP_FAILED {last_error}")

        result = response_body.get("result") if isinstance(response_body, dict) else {}
        offer_cards = result.get("offerCards") if isinstance(result, dict) else []
        if not isinstance(offer_cards, list):
            offer_cards = []
        offer_mapping_by_id: Dict[str, Dict[str, Any]] = {}
        if req.include_offer_mappings:
            fetched_mappings = await _fetch_offer_mappings_once(
                token=token,
                business_id=business_id,
                offer_ids=chunk,
                language="RU",
                modes=modes,
            )
            if fetched_mappings.get("ok"):
                for entry in _extract_offer_mapping_entries(fetched_mappings.get("body") if isinstance(fetched_mappings, dict) else {}):
                    oid = _entry_offer_id(entry)
                    if oid:
                        offer_mapping_by_id[oid] = entry

        for card in offer_cards:
            if not isinstance(card, dict):
                continue
            offer_id = str(card.get("offerId") or "").strip()
            if not offer_id:
                continue
            product = product_by_offer_id.get(offer_id)
            if not isinstance(product, dict):
                continue

            product_id = str(product.get("id") or "").strip()
            category_id = str(product.get("category_id") or "").strip()
            rows = _effective_attr_rows(category_id, attr_rows_by_cid, parent_by_id)
            row_by_param_id: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
                ym = pmap.get("yandex_market") if isinstance(pmap.get("yandex_market"), dict) else {}
                pid = str(ym.get("id") or "").strip()
                if pid and pid not in row_by_param_id:
                    row_by_param_id[pid] = row

            mapped_values: List[Dict[str, Any]] = []
            parameter_values = card.get("parameterValues") if isinstance(card.get("parameterValues"), list) else []
            content = product.get("content") if isinstance(product.get("content"), dict) else {}
            features = _cleanup_product_features(content.get("features"))
            mapping_entry = offer_mapping_by_id.get(offer_id) or {}
            imported_description = _entry_text(mapping_entry, "description")
            imported_pictures = _filter_importable_media_urls(_entry_urls(mapping_entry, "pictures"))
            imported_videos = _filter_importable_media_urls(_entry_urls(mapping_entry, "videos", "videoUrls"))
            imported_vendor = _entry_text(mapping_entry, "vendor", "vendorName", "brand")
            imported_barcodes = _entry_values(mapping_entry, "barcodes", "barcode")
            feature_by_code: Dict[str, Dict[str, Any]] = {}
            for feature in features:
                if not isinstance(feature, dict):
                    continue
                code = str(feature.get("code") or "").strip()
                if code and code not in feature_by_code:
                    feature_by_code[code] = feature

            features_changed = False
            mapping_changed = False
            for parameter in parameter_values:
                if not isinstance(parameter, dict):
                    continue
                parameter_id = str(parameter.get("parameterId") or "").strip()
                row = row_by_param_id.get(parameter_id)
                raw_value = _parameter_value_text(parameter)
                if not row or not raw_value:
                    continue
                catalog_name = str(row.get("catalog_name") or "").strip()
                dict_id = _dict_id_for_catalog_param(category_id, catalog_name, attr_value_refs_by_cid, parent_by_id)
                canonical_value = provider_import_value(dict_id, "yandex_market", raw_value)
                code = str(row.get("code") or "").strip()
                if code == "group_id" or "группа товара" in _norm(catalog_name):
                    internal_group_name = _product_group_name(product, group_name_by_id)
                    if internal_group_name:
                        canonical_value = internal_group_name
                if not code:
                    # current rows do not store code, keep same slug logic as template generation
                    from app.storage.json_store import slugify_code as _slugify_code
                    code = _slugify_code(catalog_name)
                mapped_values.append(
                    {
                        "parameterId": parameter_id,
                        "catalog_name": catalog_name,
                        "code": code,
                        "raw_value": raw_value,
                        "canonical_value": canonical_value,
                    }
                )
                if not req.apply_to_products:
                    continue
                current = feature_by_code.get(code)
                next_feature = _merge_yandex_feature_value(
                    current,
                    code=code,
                    catalog_name=catalog_name,
                    raw_value=raw_value,
                    canonical_value=canonical_value,
                    store_key=store_key,
                    store_id=store_id,
                    store_title=store_title,
                    business_id=business_id,
                    overwrite_existing=bool(req.overwrite_existing),
                )
                if current:
                    idx = next((i for i, f in enumerate(features) if isinstance(f, dict) and str(f.get("code") or "").strip() == code), -1)
                    if idx >= 0 and features[idx] != next_feature:
                        features[idx] = next_feature
                        features_changed = True
                else:
                    features.append(next_feature)
                    features_changed = True
                    feature_by_code[code] = next_feature

            if req.apply_to_products and isinstance(mapping_entry, dict) and mapping_entry:
                description_row = _find_provider_system_row(rows, "yandex_market", {"sys:description"}) or _find_system_row(rows, {"описание товара", "описание", "description", "аннотация"})
                media_row = _find_provider_system_row(rows, "yandex_market", {"sys:pictures"}) or _find_system_row(rows, {"медиа", "media", "изображения", "картинки", "фотографии товаров", "фотографии", "фото", "галерея", "gallery"})
                video_row = _find_system_row(rows, {"видео", "video", "videos"})
                vendor_row = _find_provider_system_row(rows, "yandex_market", {"sys:vendor"}) or _find_system_row(rows, {"бренд", "brand"})
                barcode_row = _find_provider_system_row(rows, "yandex_market", {"sys:barcode"}) or _find_system_row(rows, {"штрихкод", "barcode"})
                source_meta = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}

                if description_row and imported_description:
                    current_description = str(content.get("description") or "").strip()
                    if req.overwrite_existing or not current_description:
                        content["description"] = imported_description
                        mapping_changed = True
                    descriptions = source_meta.get("descriptions") if isinstance(source_meta.get("descriptions"), dict) else {}
                    descriptions["yandex_market"] = {
                        "store_id": store_id,
                        "store_title": store_title,
                        "business_id": business_id,
                        "value": imported_description,
                        "updated_at": _now_iso(),
                    }
                    source_meta["descriptions"] = descriptions

                if media_row and imported_pictures:
                    current_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
                    merged_images = _merge_media_items(current_images, imported_pictures, bool(req.overwrite_existing))
                    if merged_images != current_images:
                        content["media_images"] = merged_images
                        content["media"] = merged_images
                        mapping_changed = True
                    media_sources = source_meta.get("media_images") if isinstance(source_meta.get("media_images"), dict) else {}
                    media_sources["yandex_market"] = {
                        "store_id": store_id,
                        "store_title": store_title,
                        "business_id": business_id,
                        "count": len(imported_pictures),
                        "updated_at": _now_iso(),
                    }
                    source_meta["media_images"] = media_sources

                if video_row and imported_videos:
                    current_videos = content.get("media_videos") if isinstance(content.get("media_videos"), list) else []
                    merged_videos = _merge_media_items(current_videos, imported_videos, bool(req.overwrite_existing))
                    if merged_videos != current_videos:
                        content["media_videos"] = merged_videos
                        mapping_changed = True
                    video_sources = source_meta.get("media_videos") if isinstance(source_meta.get("media_videos"), dict) else {}
                    video_sources["yandex_market"] = {
                        "store_id": store_id,
                        "store_title": store_title,
                        "business_id": business_id,
                        "count": len(imported_videos),
                        "updated_at": _now_iso(),
                    }
                    source_meta["media_videos"] = video_sources

                if imported_vendor and _upsert_imported_system_feature(
                    features=features,
                    feature_by_code=feature_by_code,
                    row=vendor_row,
                    raw_value=imported_vendor,
                    store_key=store_key,
                    store_id=store_id,
                    store_title=store_title,
                    business_id=business_id,
                    overwrite_existing=bool(req.overwrite_existing),
                ):
                    mapping_changed = True
                    mapped_values.append(
                        {
                            "parameterId": "sys:vendor",
                            "catalog_name": str((vendor_row or {}).get("catalog_name") or "Бренд"),
                            "code": str((vendor_row or {}).get("code") or "brand"),
                            "raw_value": imported_vendor,
                            "canonical_value": imported_vendor,
                        }
                    )

                imported_barcode = next((x for x in imported_barcodes if str(x or "").strip()), "")
                if imported_barcode and _upsert_imported_system_feature(
                    features=features,
                    feature_by_code=feature_by_code,
                    row=barcode_row,
                    raw_value=imported_barcode,
                    store_key=store_key,
                    store_id=store_id,
                    store_title=store_title,
                    business_id=business_id,
                    overwrite_existing=bool(req.overwrite_existing),
                    ):
                        mapping_changed = True
                        mapped_values.append(
                        {
                            "parameterId": "sys:barcode",
                            "catalog_name": str((barcode_row or {}).get("catalog_name") or "Штрихкод"),
                            "code": str((barcode_row or {}).get("code") or "barcode"),
                            "raw_value": imported_barcode,
                            "canonical_value": imported_barcode,
                        }
                    )
                if source_meta:
                    content["source_values"] = source_meta

            existing_cache = cache_items.get(offer_id) if isinstance(cache_items.get(offer_id), dict) else {}
            cache_sources = existing_cache.get("sources") if isinstance(existing_cache.get("sources"), dict) else {}
            cache_sources[store_key] = {
                "store_id": store_id or store_key,
                "store_title": store_title or store_key,
                "business_id": business_id,
                "fetched_at": _now_iso(),
                "card": card,
                "mapped_values": mapped_values,
            }
            cache_items[offer_id] = {
                "offerId": offer_id,
                "product_id": product_id or None,
                "fetched_at": _now_iso(),
                "store_count": len(cache_sources),
                "sources": cache_sources,
            }
            existing_mapping_cache = mappings_cache_items.get(offer_id) if isinstance(mappings_cache_items.get(offer_id), dict) else {}
            mapping_sources = existing_mapping_cache.get("sources") if isinstance(existing_mapping_cache.get("sources"), dict) else {}
            mapping_sources[store_key] = {
                "store_id": store_id or store_key,
                "store_title": store_title or store_key,
                "business_id": business_id,
                "fetched_at": _now_iso(),
                "entry": mapping_entry if isinstance(mapping_entry, dict) else {},
                "description": imported_description,
                "pictures": imported_pictures,
                "videos": imported_videos,
                "vendor": imported_vendor,
                "barcodes": imported_barcodes,
            }
            mappings_cache_items[offer_id] = {
                "offerId": offer_id,
                "product_id": product_id or None,
                "fetched_at": _now_iso(),
                "store_count": len(mapping_sources),
                "sources": mapping_sources,
            }

            if (features_changed or mapping_changed) and req.apply_to_products:
                content["features"] = _cleanup_product_features(features)
                product["content"] = content
                product["updated_at"] = _now_iso()
                changed_product_ids.add(product_id)

            items_out.append(
                {
                    "offerId": offer_id,
                    "product_id": product_id or None,
                    "store_id": store_id or None,
                    "store_title": store_title or None,
                    "business_id": business_id,
                    "cardStatus": card.get("cardStatus"),
                    "contentRating": card.get("contentRating"),
                    "warnings": card.get("warnings") if isinstance(card.get("warnings"), list) else [],
                    "errors": card.get("errors") if isinstance(card.get("errors"), list) else [],
                    "recommendations": card.get("recommendations") if isinstance(card.get("recommendations"), list) else [],
                    "mapped_values": mapped_values,
                    "description": imported_description,
                    "pictures_count": len(imported_pictures),
                    "videos_count": len(imported_videos),
                }
            )

    if req.apply_to_products and changed_product_ids:
        _save_products(products)
        updated_products = len(changed_product_ids)

    cache_doc["items"] = cache_items
    _save_offer_cards_doc(cache_doc)
    mappings_doc["items"] = mappings_cache_items
    _save_offer_mappings_doc(mappings_doc)

    return {
        "ok": True,
        "count": len(items_out),
        "matched_products": len(selected),
        "updated_products": updated_products,
        "items": items_out,
    }


@router.post("/export/preview")
def yandex_export_preview(req: ExportPreviewReq) -> Dict[str, Any]:
    products = _load_products()
    nodes = _load_nodes()
    parent_by_id = _parent_map(nodes)
    mappings = _load_category_mapping()
    attr_rows_by_cid = _load_attr_mapping_rows()
    attr_value_refs_by_cid = _load_attr_value_refs()

    ids_filter = {str(x or "").strip() for x in (req.product_ids or []) if str(x or "").strip()}
    selected: List[Dict[str, Any]] = []
    for p in products:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        if ids_filter and pid not in ids_filter:
            continue
        if req.only_active and str(p.get("status") or "").strip() != "active":
            continue
        selected.append(p)
        if len(selected) >= int(req.limit):
            break

    items: List[Dict[str, Any]] = []
    ready_count = 0

    for p in selected:
        pid = str(p.get("id") or "").strip()
        category_id = str(p.get("category_id") or "").strip()
        status = str(p.get("status") or "").strip()
        yandex_category_id = _effective_yandex_category_id(category_id, mappings, parent_by_id)

        rows = _effective_attr_rows(category_id, attr_rows_by_cid, parent_by_id)
        name_row = _find_provider_system_row(rows, "yandex_market", {"sys:name"})
        vendor_row = _find_provider_system_row(rows, "yandex_market", {"sys:vendor"})
        barcode_row = _find_provider_system_row(rows, "yandex_market", {"sys:barcode"})
        description_row = _find_provider_system_row(rows, "yandex_market", {"sys:description"}) or _find_system_row(rows, {"описание товара", "описание", "description", "аннотация"})
        media_row = _find_provider_system_row(rows, "yandex_market", {"sys:pictures"}) or _find_system_row(rows, {"медиа", "media", "изображения", "картинки", "фотографии товаров", "фотографии", "фото", "галерея", "gallery"})

        offer_id = _preferred_offer_id(p)
        name = _extract_product_value(p, str((name_row or {}).get("catalog_name") or "Наименование товара")) or str(p.get("title") or "").strip()
        description = _extract_product_value(p, str((description_row or {}).get("catalog_name") or "Описание товара"))
        vendor = _extract_product_value(p, str((vendor_row or {}).get("catalog_name") or "Бренд"))
        vendor = provider_export_value(
            _dict_id_for_catalog_param(category_id, str((vendor_row or {}).get("catalog_name") or "Бренд"), attr_value_refs_by_cid, parent_by_id),
            "yandex_market",
            vendor,
        )
        barcode = _extract_product_value(p, str((barcode_row or {}).get("catalog_name") or "Штрихкод"))
        content = p.get("content") if isinstance(p.get("content"), dict) else {}
        media_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        media_legacy = content.get("media") if isinstance(content.get("media"), list) else []
        media = media_images if media_images else media_legacy
        docs = content.get("documents") if isinstance(content.get("documents"), list) else []
        pictures = [str(x.get("url") or "").strip() for x in media if isinstance(x, dict) and str(x.get("url") or "").strip()]
        manuals = [str(x.get("url") or "").strip() for x in docs if isinstance(x, dict) and str(x.get("url") or "").strip()]
        media_enabled = _is_provider_row_enabled(media_row, "yandex_market")
        description_enabled = _is_provider_row_enabled(description_row, "yandex_market")
        parameter_values: List[Dict[str, Any]] = []
        present_param_ids: Set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            pname = str(row.get("catalog_name") or "").strip()
            pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            ym = pmap.get("yandex_market") if isinstance(pmap.get("yandex_market"), dict) else {}
            if not isinstance(ym, dict) or not bool(ym.get("export")):
                continue
            ypid = str(ym.get("id") or "").strip()
            if not ypid:
                continue
            value = _extract_product_value(p, pname)
            if not value:
                continue
            value = provider_export_value(
                _dict_id_for_catalog_param(category_id, pname, attr_value_refs_by_cid, parent_by_id),
                "yandex_market",
                value,
            )
            if not value:
                continue
            present_param_ids.add(ypid)
            parameter_values.append(
                {
                    "parameterId": ypid,
                    "values": [{"value": value}],
                    "sourceCatalogName": pname,
                }
            )

        missing: List[str] = []
        if status == "archived":
            missing.append("status=archived (товар в архиве)")
        if not offer_id:
            missing.append("SKU GT (offerId) не заполнен")
        if not name:
            missing.append("Наименование товара не заполнено")
        if not yandex_category_id:
            missing.append("Нет сопоставления категории с Я.Маркет")
        if not media_enabled:
            missing.append("Не настроен блок 'Медиа' для Я.Маркет в маппинге")
        if media_enabled and not pictures:
            missing.append("Нет изображений (pictures)")
        if not vendor:
            missing.append("Бренд обязателен")
        if not description_enabled:
            missing.append("Не настроен блок 'Описание товара' для Я.Маркет в маппинге")
        if description_enabled and not description:
            missing.append("Описание (аннотация) не заполнено")

        required_param_ids = _yandex_required_param_ids(yandex_category_id) if yandex_category_id else set()
        for req_pid in sorted(required_param_ids):
            if req_pid not in present_param_ids:
                missing.append(f"Обязательный параметр Я.Маркет #{req_pid} не сопоставлен/пуст")

        ready = len(missing) == 0
        if ready:
            ready_count += 1

        payload_item = {
            "offerId": offer_id,
            "name": name,
            "description": description if description_enabled else "",
            "vendor": vendor,
            "marketCategoryId": yandex_category_id,
            "pictures": pictures if media_enabled else [],
            "manuals": manuals,
            "barcodes": [barcode] if barcode else [],
            "parameterValues": parameter_values,
        }

        items.append(
            {
                "product_id": pid,
                "ready": ready,
                "missing": missing,
                "payload_item": payload_item,
            }
        )

    return {
        "ok": True,
        "engine": "yandex_updateOfferMappings_preview",
        "items": items,
        "count": len(items),
        "ready_count": ready_count,
        "not_ready_count": max(0, len(items) - ready_count),
    }
