from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.json_store import read_doc, write_doc
from app.storage.json_store import load_templates_db, load_competitor_mapping_db
from app.storage.relational_pim_store import load_catalog_nodes
from app.api.routes.yandex_market import OfferCardsSyncReq, sync_offer_cards, ExportPreviewReq, yandex_export_preview
from app.api.routes.competitor_mapping import _ensure_row_shape, _normalize_mapped_specs
from app.core.competitors.extract_competitor_fields import extract_competitor_content

router = APIRouter(prefix="/catalog/exchange", tags=["catalog-exchange"])

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
CATALOG_PATH = DATA_DIR / "catalog_nodes.json"
IMPORT_RUNS_PATH = DATA_DIR / "catalog_import_runs.json"
EXPORT_RUNS_PATH = DATA_DIR / "catalog_export_runs.json"
CONNECTORS_STATUS_PATH = DATA_DIR / "marketplaces" / "connectors_scheduler.json"

AUTHORIZED_SITES = {
    "restore": {"restore", "re-store.ru"},
    "store77": {"store77", "store77.net", "77"},
}

_IMPORT_OVERVIEW_CACHE_TTL_SECONDS = 30.0
_import_overview_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_products() -> List[Dict[str, Any]]:
    doc = read_doc(PRODUCTS_PATH, default={"items": []})
    items = doc.get("items") if isinstance(doc, dict) else []
    return items if isinstance(items, list) else []


def _save_products(items: List[Dict[str, Any]]) -> None:
    write_doc(PRODUCTS_PATH, {"items": items})


def _load_nodes() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _load_runs(path: Path) -> Dict[str, Any]:
    doc = read_doc(path, default={"runs": {}})
    runs = doc.get("runs") if isinstance(doc, dict) else {}
    if not isinstance(runs, dict):
        runs = {}
    return {"runs": runs}


def _save_runs(path: Path, doc: Dict[str, Any]) -> None:
    write_doc(path, doc)


def _collect_subtree_ids(nodes: List[Dict[str, Any]], root_id: str) -> Set[str]:
    children: Dict[str, List[str]] = {}
    for n in nodes:
        pid = str(n.get("parent_id") or "").strip()
        nid = str(n.get("id") or "").strip()
        if nid:
            children.setdefault(pid, []).append(nid)
    out: Set[str] = set()
    stack = [str(root_id or "").strip()]
    while stack:
        cid = stack.pop()
        if not cid or cid in out:
            continue
        out.add(cid)
        stack.extend(children.get(cid, []))
    return out


def _templates_by_category(db: Dict[str, Any]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    for tid, t in templates.items():
        if not isinstance(t, dict):
            continue
        cid = str(t.get("category_id") or "").strip()
        if not cid:
            continue
        out.setdefault(cid, [])
        if tid not in out[cid]:
            out[cid].append(tid)
    cat_to_tpls = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    for cid, arr in cat_to_tpls.items():
        if not isinstance(arr, list):
            continue
        out.setdefault(str(cid), [])
        for tid in arr:
            stid = str(tid or "").strip()
            if stid and stid not in out[str(cid)]:
                out[str(cid)].append(stid)
    cat_to_tpl = db.get("category_to_template") if isinstance(db.get("category_to_template"), dict) else {}
    for cid, tid in cat_to_tpl.items():
        scid = str(cid or "").strip()
        stid = str(tid or "").strip()
        if scid and stid:
            out.setdefault(scid, [])
            if stid not in out[scid]:
                out[scid].append(stid)
    return out


def _resolve_template_id(category_id: str, nodes: List[Dict[str, Any]]) -> str:
    db = load_templates_db()
    cat_map = _templates_by_category(db)
    by_id = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict)}
    cur = by_id.get(str(category_id or "").strip())
    seen: Set[str] = set()
    while cur:
        cid = str(cur.get("id") or "").strip()
        if not cid or cid in seen:
            break
        seen.add(cid)
        tids = cat_map.get(cid) or []
        if tids:
            return str(tids[0] or "").strip()
        pid = str(cur.get("parent_id") or "").strip()
        cur = by_id.get(pid) if pid else None
    return ""


def _template_attr_defs(template_id: str) -> Dict[str, Dict[str, Any]]:
    if not template_id:
        return {}
    db = load_templates_db()
    attrs_map = db.get("attributes") if isinstance(db.get("attributes"), dict) else {}
    attrs = attrs_map.get(template_id) if isinstance(attrs_map.get(template_id), list) else []
    out: Dict[str, Dict[str, Any]] = {}
    for a in attrs:
        if not isinstance(a, dict):
            continue
        code = str(a.get("code") or "").strip()
        name = str(a.get("name") or code).strip()
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": name,
            "required": bool(a.get("required")),
            "options": a.get("options") if isinstance(a.get("options"), dict) else {},
        }
    return out


def _resolve_products(node_ids: List[str], product_ids: List[str], include_descendants: bool) -> List[Dict[str, Any]]:
    products = _load_products()
    nodes = _load_nodes()
    target_product_ids = {str(x or "").strip() for x in product_ids if str(x or "").strip()}
    target_category_ids: Set[str] = set()
    for node_id in node_ids or []:
        nid = str(node_id or "").strip()
        if not nid:
            continue
        if include_descendants:
            target_category_ids |= _collect_subtree_ids(nodes, nid)
        else:
            target_category_ids.add(nid)
    if not target_product_ids and not target_category_ids:
        return products
    out: List[Dict[str, Any]] = []
    for p in products:
        pid = str(p.get("id") or "").strip()
        cid = str(p.get("category_id") or "").strip()
        if pid in target_product_ids or cid in target_category_ids:
            out.append(p)
    return out


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _detect_site_from_url(url: str) -> str:
    host = ""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    for site, parts in AUTHORIZED_SITES.items():
        if any(part in host for part in parts):
            return site
    return ""


def _product_links_by_site(product: Dict[str, Any]) -> Dict[str, str]:
    out = {"restore": "", "store77": ""}
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    links = content.get("links") if isinstance(content.get("links"), list) else []
    for item in links:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        label = str(item.get("label") or "").strip().lower()
        if not url:
            continue
        site = _detect_site_from_url(url)
        if not site:
            if "restore" in label:
                site = "restore"
            elif "store77" in label or "77" in label:
                site = "store77"
        if site in out and not out[site]:
            out[site] = url
    return out


def _feature_index(features: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        code = str(feature.get("code") or "").strip()
        if code and code not in out:
            out[code] = feature
    return out


def _content_source_summary(product: Dict[str, Any]) -> Dict[str, Any]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    filled_features = sum(1 for f in features if isinstance(f, dict) and str(f.get("value") or "").strip())

    source_meta = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}
    descriptions = source_meta.get("descriptions") if isinstance(source_meta.get("descriptions"), dict) else {}
    media_image_sources = source_meta.get("media_images") if isinstance(source_meta.get("media_images"), dict) else {}
    media_video_sources = source_meta.get("media_videos") if isinstance(source_meta.get("media_videos"), dict) else {}
    yandex_description = bool(str(content.get("description") or "").strip()) and any(
        str(k or "").strip() == "yandex_market" or str(k or "").strip().startswith("yandex_market:")
        for k in (descriptions or {}).keys()
    )
    competitor_description = any(str(k or "").strip() in {"restore", "store77"} for k in (descriptions or {}).keys())

    images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
    videos = content.get("media_videos") if isinstance(content.get("media_videos"), list) else []
    image_urls = [str(x.get("url") or "").strip() for x in images if isinstance(x, dict) and str(x.get("url") or "").strip()]
    video_urls = [str(x.get("url") or "").strip() for x in videos if isinstance(x, dict) and str(x.get("url") or "").strip()]

    def _contains_competitor(urls: List[str]) -> bool:
        return any(_detect_site_from_url(u) in {"restore", "store77"} for u in urls)

    def _contains_yandex(urls: List[str]) -> bool:
        return any("yandex" in (urlparse(u).hostname or "").lower() for u in urls)

    return {
        "filled_features": filled_features,
        "description": {
            "present": bool(str(content.get("description") or "").strip()),
            "from_yandex": yandex_description,
            "from_competitors": competitor_description,
        },
        "media": {
            "images_count": len(image_urls),
            "videos_count": len(video_urls),
            "from_yandex": bool(media_image_sources.get("yandex_market") or media_video_sources.get("yandex_market") or _contains_yandex(image_urls) or _contains_yandex(video_urls)),
            "from_competitors": _contains_competitor(image_urls) or _contains_competitor(video_urls),
        },
        "missing_blocks": [
            *([] if str(content.get("description") or "").strip() else ["description"]),
            *([] if image_urls else ["images"]),
            *([] if filled_features else ["features"]),
        ],
    }


def _candidate_entry(source: str, label: str, value: Any, raw_value: Any = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "source": source,
        "label": label,
        "value": str(value or "").strip(),
        "raw_value": str(raw_value if raw_value is not None else value or "").strip(),
        "meta": meta or {},
    }


def _merge_conflict_payload(existing: Any, provider: str, candidates: List[Dict[str, Any]], current_value: str) -> Dict[str, Any]:
    variants = []
    seen = set()
    for item in candidates:
        key = (str(item.get("source") or ""), str(item.get("value") or ""))
        if key in seen:
            continue
        seen.add(key)
        variants.append(item)
    return {
        "provider": provider,
        "active": True,
        "current_value": current_value,
        "variants": variants,
    }


def _apply_competitor_result_to_product(
    product: Dict[str, Any],
    template_id: str,
    site: str,
    url: str,
    result: Dict[str, Any],
) -> Tuple[bool, List[Dict[str, Any]], Dict[str, Any]]:
    changed = False
    conflicts: List[Dict[str, Any]] = []
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    feature_by_code = _feature_index(features)
    attr_defs = _template_attr_defs(template_id)

    mapped_specs = result.get("mapped_specs") if isinstance(result.get("mapped_specs"), dict) else {}
    for code, candidate_value in mapped_specs.items():
        code_s = str(code or "").strip()
        value_s = str(candidate_value or "").strip()
        if not code_s or not value_s:
            continue
        feature = feature_by_code.get(code_s)
        if not feature:
            attr = attr_defs.get(code_s) or {"code": code_s, "name": code_s}
            feature = {"code": code_s, "name": str(attr.get("name") or code_s), "value": "", "selected": "custom"}
            features.append(feature)
            feature_by_code[code_s] = feature
            changed = True
        source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
        competitors = source_values.get("competitors") if isinstance(source_values.get("competitors"), dict) else {}
        prev = competitors.get(site) if isinstance(competitors.get(site), dict) else {}
        next_entry = {
            "site": site,
            "url": url,
            "raw_value": value_s,
            "canonical_value": value_s,
            "resolved_value": value_s,
            "updated_at": _now_iso(),
        }
        if prev != next_entry:
            competitors[site] = next_entry
            source_values["competitors"] = competitors
            feature["source_values"] = source_values
            changed = True

        current_value = str(feature.get("value") or "").strip()
        yandex_candidates: List[Dict[str, Any]] = []
        ym = source_values.get("yandex_market") if isinstance(source_values.get("yandex_market"), dict) else {}
        for store_key, raw in ym.items():
            if not isinstance(raw, dict):
                continue
            resolved = str(raw.get("resolved_value") or raw.get("canonical_value") or raw.get("raw_value") or "").strip()
            if not resolved:
                continue
            yandex_candidates.append(_candidate_entry(f"yandex_market:{store_key}", str(raw.get("store_title") or store_key), resolved, raw.get("raw_value"), {"store_id": raw.get("store_id"), "business_id": raw.get("business_id")}))
        comp_candidate = _candidate_entry(f"competitor:{site}", site, value_s, value_s, {"url": url})
        all_candidates = [*yandex_candidates, comp_candidate]
        unique_values = { _normalize_text(x.get("value") or "") for x in all_candidates if str(x.get("value") or "").strip() }
        unique_values.discard("")
        if not current_value and len(unique_values) == 1:
            feature["value"] = value_s
            feature.pop("conflict", None)
            changed = True
        elif len(unique_values) > 1:
            next_conflict = _merge_conflict_payload(feature.get("conflict"), "catalog_import", all_candidates, current_value)
            if feature.get("conflict") != next_conflict:
                feature["conflict"] = next_conflict
                changed = True
            conflicts.append({
                "field_code": code_s,
                "field_name": str(feature.get("name") or code_s),
                "kind": "feature",
                "current_value": current_value,
                "final_value": current_value,
                "candidates": all_candidates,
            })
        else:
            if not current_value and value_s:
                feature["value"] = value_s
                changed = True
            if feature.get("conflict"):
                feature.pop("conflict", None)
                changed = True

    description = str(content.get("description") or "").strip()
    candidate_description = str(result.get("description") or "").strip()
    if candidate_description:
        source_meta = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}
        descriptions = source_meta.get("descriptions") if isinstance(source_meta.get("descriptions"), dict) else {}
        desc_entry = {"site": site, "url": url, "value": candidate_description, "updated_at": _now_iso()}
        if descriptions.get(site) != desc_entry:
            descriptions[site] = desc_entry
            source_meta["descriptions"] = descriptions
            content["source_values"] = source_meta
            changed = True
        ym_description = description
        if not ym_description:
            description_sources = source_meta.get("yandex_market") if isinstance(source_meta.get("yandex_market"), dict) else {}
            if isinstance(description_sources, dict):
                ym_description = str(description or "").strip()
        if not description:
            content["description"] = candidate_description
            changed = True
        elif _normalize_text(description) != _normalize_text(candidate_description):
            conflicts.append({
                "field_code": "description",
                "field_name": "Описание товара",
                "kind": "description",
                "current_value": description,
                "final_value": description,
                "candidates": [
                    _candidate_entry("product:current", "Текущее", description),
                    _candidate_entry(f"competitor:{site}", site, candidate_description, candidate_description, {"url": url}),
                ],
            })

    images = result.get("images") if isinstance(result.get("images"), list) else []
    if images:
        current_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        existing_urls = {str(x.get("url") or "").strip() for x in current_images if isinstance(x, dict)}
        appended = False
        for img in images:
            url_s = str(img or "").strip()
            if not url_s or url_s in existing_urls:
                continue
            current_images.append({"url": url_s})
            existing_urls.add(url_s)
            appended = True
        if appended:
            content["media_images"] = current_images
            content["media"] = current_images
            changed = True
        source_meta = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}
        media_sources = source_meta.get("media_images") if isinstance(source_meta.get("media_images"), dict) else {}
        media_sources[site] = {"site": site, "url": url, "count": len([x for x in images if str(x or "").strip()]), "updated_at": _now_iso()}
        source_meta["media_images"] = media_sources
        content["source_values"] = source_meta
        changed = True

    if changed:
        content["features"] = features
        product["content"] = content
        product["updated_at"] = _now_iso()
    return changed, conflicts, content


class ExchangeSelection(BaseModel):
    mode: str = Field(default="all")
    node_ids: List[str] = Field(default_factory=list)
    product_ids: List[str] = Field(default_factory=list)
    include_descendants: bool = True


class CatalogImportRunReq(BaseModel):
    selection: ExchangeSelection = Field(default_factory=ExchangeSelection)
    use_yandex_market: bool = True
    use_competitors: bool = True
    overwrite_existing: bool = False
    limit: int = Field(default=1000, ge=1, le=5000)


class ConflictResolutionItem(BaseModel):
    product_id: str
    field_code: str
    field_name: str
    kind: str = "feature"
    value: str = ""


class CatalogImportResolveReq(BaseModel):
    run_id: str
    items: List[ConflictResolutionItem] = Field(default_factory=list)


class ExportTargetReq(BaseModel):
    provider: str
    store_ids: List[str] = Field(default_factory=list)


class CatalogExportRunReq(BaseModel):
    selection: ExchangeSelection = Field(default_factory=ExchangeSelection)
    targets: List[ExportTargetReq] = Field(default_factory=list)
    limit: int = Field(default=1000, ge=1, le=5000)


def _selection_key(node_ids: List[str], product_ids: List[str], include_descendants: bool, limit: int) -> str:
    return "|".join(
        [
            ",".join(sorted({str(x or "").strip() for x in node_ids if str(x or "").strip()})),
            ",".join(sorted({str(x or "").strip() for x in product_ids if str(x or "").strip()})),
            "1" if include_descendants else "0",
            str(int(limit)),
        ]
    )


def _build_import_overview_payload(
    node_ids: List[str],
    product_ids: List[str],
    include_descendants: bool,
    limit: int,
) -> Dict[str, Any]:
    products = _resolve_products(node_ids, product_ids, include_descendants)
    nodes = _load_nodes()
    product_summaries: List[Dict[str, Any]] = []
    for product in products:
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            continue
        features = (product.get("content") or {}).get("features") if isinstance((product.get("content") or {}).get("features"), list) else []
        filled = sum(1 for f in features if isinstance(f, dict) and str(f.get("value") or "").strip())
        source_summary = _content_source_summary(product)
        product_summaries.append(
            {
                "product_id": product_id,
                "title": str(product.get("title") or product_id),
                "category_id": str(product.get("category_id") or ""),
                "sku_gt": str(product.get("sku_gt") or ""),
                "filled_features": filled,
                "source_summary": source_summary,
                "conflicts_count": 0,
                "template_id": _resolve_template_id(str(product.get("category_id") or "").strip(), nodes),
            }
        )

    product_summaries.sort(
        key=lambda row: (
            0 if str(row.get("sku_gt") or "").isdigit() else 1,
            int(str(row.get("sku_gt") or "0")) if str(row.get("sku_gt") or "").isdigit() else 2**31 - 1,
            str(row.get("title") or "").lower(),
        )
    )

    import_overview = {
        "description_ready": sum(1 for row in product_summaries if bool(((row.get("source_summary") or {}).get("description") or {}).get("present"))),
        "images_ready": sum(1 for row in product_summaries if int((((row.get("source_summary") or {}).get("media") or {}).get("images_count") or 0)) > 0),
        "features_ready": sum(1 for row in product_summaries if int(((row.get("source_summary") or {}).get("filled_features") or 0)) > 0),
        "with_yandex_data": sum(
            1
            for row in product_summaries
            if bool(((row.get("source_summary") or {}).get("description") or {}).get("from_yandex"))
            or bool(((row.get("source_summary") or {}).get("media") or {}).get("from_yandex"))
        ),
        "with_competitor_media": sum(
            1 for row in product_summaries if bool(((row.get("source_summary") or {}).get("media") or {}).get("from_competitors"))
        ),
        "still_missing": sum(1 for row in product_summaries if bool((row.get("source_summary") or {}).get("missing_blocks"))),
    }

    return {
        "ok": True,
        "count": len(product_summaries),
        "products": product_summaries[: int(limit)],
        "import_overview": import_overview,
    }


@router.get("/import/overview")
def get_catalog_import_overview(
    node_ids: str = "",
    product_ids: str = "",
    include_descendants: bool = True,
    limit: int = 50,
) -> Dict[str, Any]:
    parsed_node_ids = [str(x or "").strip() for x in node_ids.split(",") if str(x or "").strip()]
    parsed_product_ids = [str(x or "").strip() for x in product_ids.split(",") if str(x or "").strip()]
    if not parsed_node_ids and not parsed_product_ids:
        return {"ok": True, "count": 0, "products": [], "import_overview": {}}

    safe_limit = max(1, min(int(limit or 50), 200))
    cache_key = _selection_key(parsed_node_ids, parsed_product_ids, bool(include_descendants), safe_limit)
    now = time.monotonic()
    cached = _import_overview_cache.get(cache_key)
    if cached and now - cached[0] < _IMPORT_OVERVIEW_CACHE_TTL_SECONDS:
        return cached[1]

    payload = _build_import_overview_payload(parsed_node_ids, parsed_product_ids, bool(include_descendants), safe_limit)
    _import_overview_cache[cache_key] = (now, payload)
    return payload


@router.post("/import/run")
async def run_catalog_import(req: CatalogImportRunReq) -> Dict[str, Any]:
    _import_overview_cache.clear()
    products = _resolve_products(req.selection.node_ids, req.selection.product_ids, bool(req.selection.include_descendants))
    products = products[: int(req.limit)]
    if not products:
        return {"ok": True, "count": 0, "updated_products": 0, "conflicts": [], "run_id": ""}

    target_product_ids = [str(p.get("id") or "").strip() for p in products if str(p.get("id") or "").strip()]
    yandex_result: Dict[str, Any] = {"ok": True, "count": 0, "matched_products": 0, "updated_products": 0, "items": []}
    if req.use_yandex_market:
        yandex_result = await sync_offer_cards(
            OfferCardsSyncReq(
                product_ids=target_product_ids,
                apply_to_products=True,
                overwrite_existing=bool(req.overwrite_existing),
                limit=min(int(req.limit), 5000),
                include_offer_mappings=True,
                with_recommendations=True,
            )
        )

    # reload products after yandex sync
    products_doc = _load_products()
    product_map = {str(p.get("id") or "").strip(): p for p in products_doc if isinstance(p, dict)}
    nodes = _load_nodes()
    competitor_db = load_competitor_mapping_db()

    total_changed_ids: Set[str] = set()
    product_summaries: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []

    for product_id in target_product_ids:
        product = product_map.get(product_id)
        if not isinstance(product, dict):
            continue
        template_id = _resolve_template_id(str(product.get("category_id") or "").strip(), nodes)
        links_by_site = _product_links_by_site(product)
        product_conflicts: List[Dict[str, Any]] = []
        competitor_results: Dict[str, Any] = {}
        if req.use_competitors and template_id:
            row = _ensure_row_shape((competitor_db.get("templates", {}) or {}).get(template_id) or {})
            mapping_by_site = row.get("mapping_by_site") if isinstance(row.get("mapping_by_site"), dict) else {"restore": {}, "store77": {}}
            for site in ("restore", "store77"):
                url = str(links_by_site.get(site) or "").strip()
                if not url:
                    continue
                try:
                    raw_result = await extract_competitor_content(url)
                except Exception as e:
                    competitor_results[site] = {"ok": False, "error": str(e) or "EXTRACT_FAILED", "url": url}
                    continue
                specs = raw_result.get("specs") if isinstance(raw_result.get("specs"), dict) else {}
                mapped_raw: Dict[str, str] = {}
                if isinstance(mapping_by_site.get(site), dict):
                    norm_specs = {" ".join(str(k or "").split()).lower(): str(v or "").strip() for k, v in specs.items() if str(k or "").strip()}
                    for code, field in mapping_by_site.get(site, {}).items():
                        fkey = " ".join(str(field or "").split()).lower()
                        value = norm_specs.get(fkey, "")
                        if value:
                            mapped_raw[str(code or "").strip()] = value
                normalized = _normalize_mapped_specs(template_id, mapped_raw) if mapped_raw else {}
                comp_payload = {
                    "ok": True,
                    "url": url,
                    "description": str(raw_result.get("description") or "").strip(),
                    "images": raw_result.get("images") if isinstance(raw_result.get("images"), list) else [],
                    "specs": specs,
                    "mapped_specs": normalized,
                }
                competitor_results[site] = comp_payload
                changed, field_conflicts, _ = _apply_competitor_result_to_product(product, template_id, site, url, comp_payload)
                if changed:
                    total_changed_ids.add(product_id)
                for c in field_conflicts:
                    c["product_id"] = product_id
                    c["product_title"] = str(product.get("title") or product_id)
                    c["template_id"] = template_id
                product_conflicts.extend(field_conflicts)

        if product_id in total_changed_ids:
            product["updated_at"] = _now_iso()
        features = (product.get("content") or {}).get("features") if isinstance((product.get("content") or {}).get("features"), list) else []
        filled = sum(1 for f in features if isinstance(f, dict) and str(f.get("value") or "").strip())
        source_summary = _content_source_summary(product)
        competitor_compact = {
            site: {
                "ok": bool(data.get("ok")),
                "images_count": len(data.get("images") or []) if isinstance(data, dict) else 0,
                "has_description": bool(str((data or {}).get("description") or "").strip()) if isinstance(data, dict) else False,
                "mapped_specs_count": len((data or {}).get("mapped_specs") or {}) if isinstance(data, dict) else 0,
                "error": str((data or {}).get("error") or "").strip() if isinstance(data, dict) else "",
            }
            for site, data in competitor_results.items()
        }
        product_summaries.append({
            "product_id": product_id,
            "title": str(product.get("title") or product_id),
            "category_id": str(product.get("category_id") or ""),
            "sku_gt": str(product.get("sku_gt") or ""),
            "filled_features": filled,
            "source_summary": source_summary,
            "competitor_results": competitor_compact,
            "conflicts_count": len(product_conflicts),
        })
        conflicts.extend(product_conflicts)

    if total_changed_ids:
        _save_products(products_doc)

    import_overview = {
        "description_ready": sum(1 for row in product_summaries if bool(((row.get("source_summary") or {}).get("description") or {}).get("present"))),
        "images_ready": sum(1 for row in product_summaries if int((((row.get("source_summary") or {}).get("media") or {}).get("images_count") or 0)) > 0),
        "features_ready": sum(1 for row in product_summaries if int(((row.get("source_summary") or {}).get("filled_features") or 0)) > 0),
        "with_yandex_data": sum(
            1
            for row in product_summaries
            if bool(((row.get("source_summary") or {}).get("description") or {}).get("from_yandex"))
            or bool(((row.get("source_summary") or {}).get("media") or {}).get("from_yandex"))
        ),
        "with_competitor_media": sum(
            1 for row in product_summaries if bool(((row.get("source_summary") or {}).get("media") or {}).get("from_competitors"))
        ),
        "still_missing": sum(1 for row in product_summaries if bool((row.get("source_summary") or {}).get("missing_blocks"))),
    }

    run_id = f"import_{uuid4().hex[:10]}"
    runs = _load_runs(IMPORT_RUNS_PATH)
    runs["runs"][run_id] = {
        "id": run_id,
        "created_at": _now_iso(),
        "selection": req.selection.model_dump(),
        "summary": {
            "count": len(target_product_ids),
            "yandex_result": yandex_result,
            "updated_products": len(total_changed_ids) + int(yandex_result.get("updated_products") or 0),
            "conflicts_count": len(conflicts),
            "import_overview": import_overview,
        },
        "products": product_summaries,
        "conflicts": conflicts,
        "resolved": [],
    }
    _save_runs(IMPORT_RUNS_PATH, runs)

    return {
        "ok": True,
        "run_id": run_id,
        "count": len(target_product_ids),
        "updated_products": len(total_changed_ids) + int(yandex_result.get("updated_products") or 0),
        "conflicts": conflicts,
        "products": product_summaries,
        "yandex_result": yandex_result,
        "import_overview": import_overview,
    }


@router.get("/import/runs/{run_id}")
def get_catalog_import_run(run_id: str) -> Dict[str, Any]:
    runs = _load_runs(IMPORT_RUNS_PATH)
    row = (runs.get("runs") or {}).get(run_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return {"ok": True, "run": row}


@router.post("/import/resolve")
def resolve_catalog_import(req: CatalogImportResolveReq) -> Dict[str, Any]:
    _import_overview_cache.clear()
    runs = _load_runs(IMPORT_RUNS_PATH)
    run = (runs.get("runs") or {}).get(req.run_id)
    if not isinstance(run, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    products = _load_products()
    by_id = {str(p.get("id") or "").strip(): p for p in products if isinstance(p, dict)}
    resolved_keys: Set[Tuple[str, str]] = set()
    changed_ids: Set[str] = set()
    for item in req.items or []:
        pid = str(item.product_id or "").strip()
        code = str(item.field_code or "").strip()
        if not pid or not code:
            continue
        product = by_id.get(pid)
        if not isinstance(product, dict):
            continue
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        if item.kind == "description":
            content["description"] = str(item.value or "")
            product["content"] = content
            product["updated_at"] = _now_iso()
            changed_ids.add(pid)
            resolved_keys.add((pid, code))
            continue
        features = content.get("features") if isinstance(content.get("features"), list) else []
        for feature in features:
            if not isinstance(feature, dict):
                continue
            fcode = str(feature.get("code") or "").strip()
            if fcode != code:
                continue
            feature["value"] = str(item.value or "")
            if isinstance(feature.get("conflict"), dict):
                feature["conflict"]["active"] = False
                feature["conflict"]["resolved_value"] = str(item.value or "")
            product["content"] = content
            product["updated_at"] = _now_iso()
            changed_ids.add(pid)
            resolved_keys.add((pid, code))
            break
    if changed_ids:
        _save_products(products)
    resolved = run.get("resolved") if isinstance(run.get("resolved"), list) else []
    for pid, code in resolved_keys:
        key = f"{pid}:{code}"
        if key not in resolved:
            resolved.append(key)
    run["resolved"] = resolved
    conflicts = run.get("conflicts") if isinstance(run.get("conflicts"), list) else []
    next_conflicts = []
    for row in conflicts:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("product_id") or "").strip(), str(row.get("field_code") or "").strip())
        if key in resolved_keys:
            row = {**row, "resolved": True}
        next_conflicts.append(row)
    run["conflicts"] = next_conflicts
    run["updated_at"] = _now_iso()
    runs["runs"][req.run_id] = run
    _save_runs(IMPORT_RUNS_PATH, runs)
    return {"ok": True, "resolved_count": len(resolved_keys)}


@router.post("/export/run")
def run_catalog_export(req: CatalogExportRunReq) -> Dict[str, Any]:
    products = _resolve_products(req.selection.node_ids, req.selection.product_ids, bool(req.selection.include_descendants))
    products = products[: int(req.limit)]
    product_ids = [str(p.get("id") or "").strip() for p in products if str(p.get("id") or "").strip()]
    state = read_doc(CONNECTORS_STATUS_PATH, default={"providers": {}})
    providers_state = state.get("providers") if isinstance(state, dict) else {}
    if not isinstance(providers_state, dict):
        providers_state = {}
    batches: List[Dict[str, Any]] = []
    for target in req.targets or []:
        provider = str(target.provider or "").strip()
        if provider == "yandex_market":
            preview = yandex_export_preview(ExportPreviewReq(product_ids=product_ids, only_active=False, limit=len(product_ids) or 1000))
            stores = (providers_state.get("yandex_market") or {}).get("import_stores") if isinstance((providers_state.get("yandex_market") or {}).get("import_stores"), list) else []
            selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
            selected_stores = [s for s in stores if str(s.get("id") or "").strip() in selected_store_ids] if selected_store_ids else [s for s in stores if bool(s.get("enabled", True))]
            if not selected_stores:
                selected_stores = [{"id": "default", "title": "Все магазины"}]
            for store in selected_stores:
                batches.append({
                    "provider": provider,
                    "store_id": str(store.get("id") or "default"),
                    "store_title": str(store.get("title") or "Все магазины"),
                    "status": "preview_ready",
                    "ready_count": int(preview.get("ready_count") or 0),
                    "count": int(preview.get("count") or 0),
                    "items": preview.get("items") if isinstance(preview.get("items"), list) else [],
                })
        elif provider == "ozon":
            stores = (providers_state.get("ozon") or {}).get("import_stores") if isinstance((providers_state.get("ozon") or {}).get("import_stores"), list) else []
            selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
            selected_stores = [s for s in stores if str(s.get("id") or "").strip() in selected_store_ids] if selected_store_ids else [s for s in stores if bool(s.get("enabled", True))]
            if not selected_stores:
                selected_stores = [{"id": "default", "title": "Все магазины"}]
            for store in selected_stores:
                batches.append({
                    "provider": provider,
                    "store_id": str(store.get("id") or "default"),
                    "store_title": str(store.get("title") or "Все магазины"),
                    "status": "not_implemented",
                    "ready_count": 0,
                    "count": len(product_ids),
                    "items": [],
                })
    run_id = f"export_{uuid4().hex[:10]}"
    runs = _load_runs(EXPORT_RUNS_PATH)
    runs["runs"][run_id] = {
        "id": run_id,
        "created_at": _now_iso(),
        "selection": req.selection.model_dump(),
        "targets": [t.model_dump() for t in req.targets or []],
        "summary": {
            "count": len(product_ids),
            "batches": len(batches),
        },
        "batches": batches,
    }
    _save_runs(EXPORT_RUNS_PATH, runs)
    return {"ok": True, "run_id": run_id, "count": len(product_ids), "batches": batches}


@router.get("/export/runs/{run_id}")
def get_catalog_export_run(run_id: str) -> Dict[str, Any]:
    runs = _load_runs(EXPORT_RUNS_PATH)
    row = (runs.get("runs") or {}).get(run_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return {"ok": True, "run": row}
