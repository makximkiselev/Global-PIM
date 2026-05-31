from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.connectors_state import ConnectorsStateReadAdapter
from app.core.json_store import read_doc, write_doc
from app.core.media import dedupe_media_items, media_identity_keys
from app.core.products.parameter_flow import dict_id_for_product_feature
from app.core.tenant_context import current_tenant_organization_id
from app.core.value_mapping import provider_export_value_details
from app.storage.json_store import load_templates_db, load_competitor_mapping_db
from app.storage.relational_pim_store import (
    bulk_upsert_product_items,
    claim_pim_workflow_run_as_running,
    get_pim_workflow_run,
    list_pim_channel_links,
    list_pim_workflow_runs,
    load_catalog_nodes,
    query_products_full,
    upsert_pim_workflow_run,
)
from app.api.routes.yandex_market import (
    OfferCardsSyncReq,
    sync_offer_cards,
    ExportPreviewReq,
    yandex_export_preview,
    _effective_attr_rows,
    _extract_product_value,
    _load_attr_mapping_rows,
    _load_category_mapping,
    _parent_map,
    _preferred_offer_id,
    _export_media_url,
    _export_media_urls,
)
from app.api.routes.ozon_market import OzonProductsSyncReq, sync_product_statuses
from app.api.routes.competitor_mapping import (
    _ai_map_competitor_specs_to_template,
    _confirmed_links_for_product,
    _clean_competitor_description_for_product,
    _ensure_row_shape,
    _fetch_store77_images_with_browser,
    _import_competitor_image_to_storage,
    _is_protected_product_content_field,
    _normalize_mapped_specs,
    _upload_competitor_image_bytes,
    _extract_competitor_content_with_retry,
)

router = APIRouter(prefix="/catalog/exchange", tags=["catalog-exchange"])

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
PRODUCTS_PATH = DATA_DIR / "products.json"
CATALOG_PATH = DATA_DIR / "catalog_nodes.json"
IMPORT_RUNS_PATH = DATA_DIR / "catalog_import_runs.json"
EXPORT_RUNS_PATH = DATA_DIR / "catalog_export_runs.json"
OZON_CATEGORIES_TREE_PATH = DATA_DIR / "marketplaces" / "ozon" / "categories_tree.json"

_EXPORT_WORKFLOW = "catalog_export_prepare"
_EXPORT_JOB_TTL_SECONDS = 900.0
OZON_TECHNICAL_EXPORT_PRICE = "1000000"
COMPETITOR_MEDIA_PER_SOURCE_LIMIT = 12

AUTHORIZED_SITES = {
    "restore": {"restore", "re-store.ru"},
    "store77": {"store77", "store77.net", "77"},
}

_IMPORT_OVERVIEW_CACHE_TTL_SECONDS = 30.0
_IMPORT_OVERVIEW_CACHE_MAX_ITEMS = int(os.getenv("IMPORT_OVERVIEW_CACHE_MAX_ITEMS", "20") or "20")
_import_overview_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _remember_import_overview(cache_key: str, payload: Dict[str, Any]) -> None:
    now = time.monotonic()
    for key, cached in list(_import_overview_cache.items()):
        if now - float(cached[0] or 0.0) >= _IMPORT_OVERVIEW_CACHE_TTL_SECONDS:
            _import_overview_cache.pop(key, None)
    _import_overview_cache[cache_key] = (now, payload)
    while len(_import_overview_cache) > max(1, _IMPORT_OVERVIEW_CACHE_MAX_ITEMS):
        oldest_key = min(_import_overview_cache, key=lambda key: _import_overview_cache[key][0])
        _import_overview_cache.pop(oldest_key, None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_products() -> List[Dict[str, Any]]:
    return query_products_full()


def _save_products(items: List[Dict[str, Any]]) -> None:
    bulk_upsert_product_items(items)


def _load_nodes() -> List[Dict[str, Any]]:
    return load_catalog_nodes()


def _media_items_for_export_review(media: Any) -> List[Dict[str, Any]]:
    return [
        item
        for item in (media if isinstance(media, list) else [])
        if isinstance(item, dict) and item.get("selected") is not False and str(item.get("url") or "").strip()
    ]


def _media_review_count(media: Any) -> int:
    count = 0
    for item in _media_items_for_export_review(media):
        status = str(item.get("status") or "").strip().lower()
        source_type = str(item.get("source_type") or "").strip().lower()
        if status == "needs_review" or item.get("needs_review") is True or source_type == "external_hotlink":
            count += 1
    return count


def _missing_detail(code: str, message: str, target: str, **extra: Any) -> Dict[str, Any]:
    out = {"code": code, "message": message, "target": target}
    out.update({k: v for k, v in extra.items() if v not in (None, "")})
    return out


def _load_runs(path: Path) -> Dict[str, Any]:
    doc = read_doc(path, default={"runs": {}})
    runs = doc.get("runs") if isinstance(doc, dict) else {}
    if not isinstance(runs, dict):
        runs = {}
    return {"runs": runs}


def _run_sort_value(run: Dict[str, Any]) -> str:
    for key in ("created_at", "started_at", "finished_at", "updated_at"):
        value = str(run.get(key) or "").strip()
        if value:
            return value
    return str(run.get("id") or "")


def _prune_runs_doc(path: Path, doc: Dict[str, Any]) -> Dict[str, Any]:
    runs = doc.get("runs") if isinstance(doc.get("runs"), dict) else {}
    if not isinstance(runs, dict):
        return {"runs": {}}
    default_limit = 30 if path == EXPORT_RUNS_PATH else 50
    try:
        keep = max(1, int(os.getenv("CATALOG_EXCHANGE_RUN_HISTORY_LIMIT", str(default_limit)) or default_limit))
    except Exception:
        keep = default_limit
    if len(runs) <= keep:
        return {"runs": runs}
    ordered = sorted(
        [(run_id, run) for run_id, run in runs.items() if isinstance(run, dict)],
        key=lambda item: _run_sort_value(item[1]),
        reverse=True,
    )
    return {"runs": {run_id: run for run_id, run in ordered[:keep]}}


def _save_runs(path: Path, doc: Dict[str, Any]) -> None:
    write_doc(path, _prune_runs_doc(path, doc))


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


def _field_key(value: Any) -> str:
    normalized = str(value or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", normalized).strip()


_COMPETITOR_SPEC_TO_PIM_ALIASES: Dict[str, List[str]] = {
    "встроенная память": ["память", "объем встроенной памяти", "объём встроенной памяти", "накопитель", "rom"],
    "оперативная память": ["объем оперативной памяти", "объём оперативной памяти", "ram", "озу"],
    "название цвета от производителя": ["цвет", "цвет товара", "цвет корпуса"],
    "количество sim карт": ["sim карта", "sim-карта", "тип sim карты", "тип sim-карты", "количество sim карт"],
    "линейка": ["серия", "модельный ряд"],
    "подробная комплектация": ["в комплекте", "комплектация"],
    "страна производства": ["страна производителя", "производитель страна"],
    "гарантийный срок": ["гарантия", "гарантия мес", "гарантия, мес"],
    "аутентификация": ["тип разблокировки", "разблокировка"],
    "функции зарядки": ["поддержка magsafe", "беспроводная зарядка", "быстрая зарядка"],
    "беспроводные интерфейсы": ["интерфейсы", "беспроводные технологии"],
    "навигационная система": ["спутниковая навигация", "навигация"],
    "степень защиты": ["защита от воды", "уровень защиты от влаги", "влагозащита"],
    "тип разъема для зарядки": ["разъем", "разъём", "порт зарядки", "интерфейс зарядки"],
    "разрешение экрана": ["размер изображения", "разрешение дисплея"],
    "тип матрицы экрана": ["тип экрана", "тип дисплея", "технология экрана"],
    "число пикселей на дюйм": ["число пикселей на дюйм ppi", "ppi"],
    "стандарт связи": ["стандарт", "сети", "мобильная связь"],
    "характеристики основной камеры": ["тыловая фотокамера", "основная камера", "разрешение камеры", "тип объектива"],
    "функции камеры": ["функции тыловой фотокамеры", "функции основной камеры", "технологии камеры"],
    "максимальное разрешение видеосъемки": ["разрешение видео", "видеосъемка"],
    "вес устройства г": ["вес", "вес г", "вес товара"],
    "материал корпуса": ["материал"],
    "датчики": ["сенсоры"],
    "максимальная яркость": ["яркость", "яркость экрана"],
    "контрастность экрана": ["контрастность"],
    "тип аккумулятора": ["тип аккумулятора"],
    "крепление аккумулятора": ["аккумулятор"],
    "время работы в режиме прослушивания музыки": ["воспроизведение аудио"],
    "время в режиме воспроизведения видео": ["воспроизведение видео", "проигрывание видео"],
    "время работы в режиме воспроизведения видео": ["воспроизведение видео", "проигрывание видео"],
    "высота устройства мм": ["высота", "высота мм"],
    "ширина устройства мм": ["ширина", "ширина мм"],
    "толщина": ["толщина мм"],
}


def _auto_map_competitor_specs(template_id: str, specs: Dict[str, Any], explicit_mapping: Dict[str, Any]) -> Dict[str, str]:
    attr_defs = _template_attr_defs(template_id)
    if not attr_defs or not isinstance(specs, dict):
        return {}
    spec_by_key = {
        _field_key(key): str(value or "").strip()
        for key, value in specs.items()
        if str(key or "").strip() and str(value or "").strip()
    }
    mapped: Dict[str, str] = {}
    for code, field in (explicit_mapping or {}).items():
        code_s = str(code or "").strip()
        attr = attr_defs.get(code_s) or {}
        if _is_protected_product_content_field(code_s, attr.get("name")):
            continue
        fkey = _field_key(field)
        if code_s and fkey and spec_by_key.get(fkey):
            mapped[code_s] = spec_by_key[fkey]

    attr_lookup: Dict[str, str] = {}
    for code, attr in attr_defs.items():
        name = str(attr.get("name") or code).strip()
        if _is_protected_product_content_field(code, name):
            continue
        for key in {_field_key(code), _field_key(name)}:
            if key:
                attr_lookup.setdefault(key, code)
        for alias in _COMPETITOR_SPEC_TO_PIM_ALIASES.get(_field_key(name), []):
            attr_lookup.setdefault(_field_key(alias), code)

    for spec_key, value in spec_by_key.items():
        code = attr_lookup.get(spec_key)
        if code and code not in mapped:
            mapped[code] = value
    return mapped


def _resolve_products(node_ids: List[str], product_ids: List[str], include_descendants: bool, limit: int = 0) -> List[Dict[str, Any]]:
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
        return query_products_full(limit=limit if limit > 0 else None)
    by_id: Dict[str, Dict[str, Any]] = {}
    if target_product_ids:
        for row in query_products_full(ids=sorted(target_product_ids)):
            pid = str(row.get("id") or "").strip()
            if pid and pid not in by_id:
                by_id[pid] = row
    if target_category_ids and (limit <= 0 or len(by_id) < limit):
        remaining = max(0, limit - len(by_id)) if limit > 0 else 0
        for row in query_products_full(category_ids=sorted(target_category_ids), limit=remaining or None):
            pid = str(row.get("id") or "").strip()
            if pid and pid not in by_id:
                by_id[pid] = row
    return list(by_id.values())


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _variant_family_key(product: Dict[str, Any]) -> str:
    title = _normalize_text(product.get("title"))
    if not title:
        return ""
    model_patterns = (
        r"\biphone\s+\d+\s+pro(?:\s+max)?\b",
        r"\bipad\s+air\s+\d+\s+m\d+\b",
        r"\bmacbook\s+air\s+\d+\s+m\d+\b",
        r"\bmacbook\s+pro\s+\d+\s+m\d+\b",
    )
    model = ""
    for pattern in model_patterns:
        match = re.search(pattern, title)
        if match:
            model = " ".join(match.group(0).split())
            break
    color = ""
    for candidate in (
        "space grey",
        "space gray",
        "sky blue",
        "silver",
        "orange",
        "blue",
        "black",
        "white",
        "purple",
        "midnight",
        "starlight",
        "серебрист",
        "серый",
        "оранж",
        "син",
        "фиолет",
        "сияющая звезда",
    ):
        if candidate in title:
            color = candidate
            break
    if not model or not color:
        return ""
    category_id = str(product.get("category_id") or "").strip()
    return "|".join([category_id, model, color])


def _ensure_feature(features: List[Dict[str, Any]], code: str, name: str, value: str, source_product_id: str) -> bool:
    clean_value = str(value or "").strip()
    if not clean_value:
        return False
    for feature in features:
        if not isinstance(feature, dict):
            continue
        if str(feature.get("code") or "").strip() == code or _normalize_text(feature.get("name")) == _normalize_text(name):
            if str(feature.get("value") or "").strip():
                return False
            feature["value"] = clean_value
            feature["source"] = "variant_sibling"
            feature["source_product_id"] = source_product_id
            return True
    features.append({"code": code, "name": name, "value": clean_value, "source": "variant_sibling", "source_product_id": source_product_id})
    return True


def _hydrate_missing_content_from_variant_siblings(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for product in products:
        key = _variant_family_key(product)
        if key:
            by_key.setdefault(key, []).append(product)

    changed: List[Dict[str, Any]] = []
    for product in products:
        key = _variant_family_key(product)
        siblings = [item for item in by_key.get(key, []) if str(item.get("id") or "") != str(product.get("id") or "")]
        if not siblings:
            continue
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        features = content.get("features") if isinstance(content.get("features"), list) else []
        source_meta = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}
        product_changed = False

        if not str(content.get("description") or "").strip():
            for sibling in siblings:
                sibling_content = sibling.get("content") if isinstance(sibling.get("content"), dict) else {}
                description = str(sibling_content.get("description") or "").strip()
                if not description:
                    continue
                content["description"] = description
                descriptions = source_meta.get("descriptions") if isinstance(source_meta.get("descriptions"), dict) else {}
                descriptions["variant_sibling"] = {"source_product_id": str(sibling.get("id") or ""), "updated_at": _now_iso()}
                source_meta["descriptions"] = descriptions
                product_changed = True
                break

        current_media = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        if not current_media:
            for sibling in siblings:
                sibling_content = sibling.get("content") if isinstance(sibling.get("content"), dict) else {}
                sibling_media = sibling_content.get("media_images") if isinstance(sibling_content.get("media_images"), list) else []
                if not sibling_media:
                    continue
                content["media_images"] = [dict(item, source=item.get("source") or "variant_sibling", source_product_id=str(sibling.get("id") or "")) for item in deepcopy(sibling_media) if isinstance(item, dict)]
                content.pop("media", None)
                media_sources = source_meta.get("media_images") if isinstance(source_meta.get("media_images"), dict) else {}
                media_sources["variant_sibling"] = {"source_product_id": str(sibling.get("id") or ""), "count": len(content["media_images"]), "updated_at": _now_iso()}
                source_meta["media_images"] = media_sources
                product_changed = True
                break

        if not _extract_product_value(product, "Бренд"):
            for sibling in siblings:
                brand = _extract_product_value(sibling, "Бренд")
                if _ensure_feature(features, "brand", "Бренд", brand, str(sibling.get("id") or "")):
                    product_changed = True
                    break

        if product_changed:
            content["features"] = features
            if source_meta:
                content["source_values"] = source_meta
            product["content"] = content
            product["updated_at"] = _now_iso()
            changed.append(product)
    return changed


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


def _product_partner_links_by_site(product: Dict[str, Any], competitor_db: Dict[str, Any]) -> Dict[str, str]:
    out = _product_links_by_site(product)
    product_id = str(product.get("id") or "").strip()
    if not product_id:
        return out
    discovery = competitor_db.get("discovery") if isinstance(competitor_db.get("discovery"), dict) else {}
    for link in _confirmed_links_for_product(discovery, product_id):
        if not isinstance(link, dict):
            continue
        site = str(link.get("source_id") or "").strip()
        url = str(link.get("url") or "").strip()
        if site in out and url:
            out[site] = url
    return out


def _export_partner_links_by_site(product_id: str, min_score: float = 0.9) -> Dict[str, str]:
    normalized_product_id = str(product_id or "").strip()
    out = {"restore": "", "store77": ""}
    if not normalized_product_id:
        return out
    best: Dict[str, Tuple[float, str]] = {}
    try:
        rows = list_pim_channel_links(
            scope="competitor_product",
            entity_type="product",
            entity_id=normalized_product_id,
        )
    except Exception:
        return out
    for row in rows:
        status = str(row.get("status") or "").strip()
        if status != "confirmed":
            continue
        provider = str(row.get("provider") or "").strip()
        url = str(row.get("url") or "").strip()
        if provider not in out or not url or _detect_site_from_url(url) != provider:
            continue
        try:
            score = float(row.get("score") or 0.0)
        except Exception:
            score = 0.0
        if score < min_score:
            continue
        current = best.get(provider)
        if current and current[0] >= score:
            continue
        best[provider] = (score, url)
    for provider, (_, url) in best.items():
        out[provider] = url
    return out


async def _enrich_export_products_from_candidate_media(products: List[Dict[str, Any]]) -> Set[str]:
    nodes = _load_nodes()
    changed_ids: Set[str] = set()
    try:
        max_products = max(0, int(os.getenv("EXPORT_CANDIDATE_MEDIA_ENRICH_LIMIT", "0") or "0"))
    except Exception:
        max_products = 0
    try:
        concurrency = max(1, int(os.getenv("EXPORT_CANDIDATE_MEDIA_ENRICH_CONCURRENCY", "6") or "6"))
    except Exception:
        concurrency = 6
    try:
        timeout_seconds = max(5.0, float(os.getenv("EXPORT_CANDIDATE_MEDIA_ENRICH_TIMEOUT", "18") or "18"))
    except Exception:
        timeout_seconds = 18.0
    candidates = products[:max_products] if max_products else []
    semaphore = asyncio.Semaphore(concurrency)
    save_lock = asyncio.Lock()

    async def _one(product: Dict[str, Any]) -> None:
        if not isinstance(product, dict):
            return
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            return
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        current_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        if current_images:
            return
        template_id = _resolve_template_id(str(product.get("category_id") or "").strip(), nodes)
        if not template_id:
            return
        partner_links = _export_partner_links_by_site(product_id)
        for site in ("store77", "restore"):
            url = str(partner_links.get(site) or "").strip()
            if not url:
                continue
            async with semaphore:
                try:
                    raw_result = await _extract_competitor_content_with_retry(url, attempts=1)
                except Exception:
                    continue
                payload = {
                    "ok": True,
                    "url": url,
                    "description": str(raw_result.get("description") or "").strip(),
                    "images": raw_result.get("images") if isinstance(raw_result.get("images"), list) else [],
                    "specs": raw_result.get("specs") if isinstance(raw_result.get("specs"), dict) else {},
                    "mapped_specs": {},
                }
                changed, _, _ = await _apply_competitor_result_to_product(product, template_id, site, url, payload)
                if changed:
                    async with save_lock:
                        _save_products([product])
                    changed_ids.add(product_id)
                    content = product.get("content") if isinstance(product.get("content"), dict) else {}
                    current_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
                    if current_images:
                        break

    tasks = [asyncio.create_task(_one(product)) for product in candidates]
    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task.exception():
                continue
    return changed_ids


def _feature_index(features: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, dict):
            continue
        code = str(feature.get("code") or "").strip()
        if code and code not in out:
            out[code] = feature
    return out


def _media_identity_keys(item: Dict[str, Any]) -> Set[str]:
    return media_identity_keys(item)


def _dedupe_media_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return dedupe_media_items(items)


def _competitor_media_per_source_limit() -> int:
    raw = str(os.getenv("COMPETITOR_MEDIA_PER_SOURCE_LIMIT") or "").strip()
    if not raw:
        return COMPETITOR_MEDIA_PER_SOURCE_LIMIT
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return COMPETITOR_MEDIA_PER_SOURCE_LIMIT


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
    media_sources = {
        str(x.get("source") or "").strip()
        for x in [*images, *videos]
        if isinstance(x, dict) and str(x.get("source") or "").strip()
    }
    media_external_urls = [
        str(x.get("external_url") or x.get("source_url") or "").strip()
        for x in [*images, *videos]
        if isinstance(x, dict) and str(x.get("external_url") or x.get("source_url") or "").strip()
    ]

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
            "from_competitors": bool(
                media_image_sources.get("restore")
                or media_image_sources.get("store77")
                or media_video_sources.get("restore")
                or media_video_sources.get("store77")
                or media_sources.intersection({"restore", "store77"})
                or _contains_competitor(image_urls)
                or _contains_competitor(video_urls)
                or _contains_competitor(media_external_urls)
            ),
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


async def _apply_competitor_result_to_product(
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
        attr = attr_defs.get(code_s) or {}
        if _is_protected_product_content_field(code_s, attr.get("name")):
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
    candidate_description = _clean_competitor_description_for_product(result.get("description"))
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
        current_images = _dedupe_media_items([item for item in current_images if isinstance(item, dict)])
        source_limit = _competitor_media_per_source_limit()
        source_count = sum(
            1
            for item in current_images
            if isinstance(item, dict)
            and str(item.get("source") or "").strip() == site
            and str(item.get("source_url") or "").strip() == url
        )
        existing_urls = {str(x.get("url") or "").strip() for x in current_images if isinstance(x, dict)}
        existing_external_urls = {
            key
            for item in current_images
            if isinstance(item, dict)
            for key in _media_identity_keys(item)
        }
        browser_image_payloads: Dict[str, Tuple[bytes, str]] = {}
        store77_browser_fetch_attempted = False
        appended = False
        for img in images:
            if source_count >= source_limit:
                break
            url_s = str(img or "").strip()
            if not url_s or url_s in existing_urls or url_s in existing_external_urls:
                continue
            imported = await _import_competitor_image_to_storage(
                image_url=url_s,
                product=product,
                source_id=site,
                source_url=url,
            )
            if not imported and site == "store77":
                if not store77_browser_fetch_attempted:
                    browser_image_payloads = await _fetch_store77_images_with_browser(
                        [str(x or "").strip() for x in images],
                        url,
                    )
                    store77_browser_fetch_attempted = True
                if url_s in browser_image_payloads:
                    body, content_type = browser_image_payloads[url_s]
                    imported = _upload_competitor_image_bytes(
                        image_url=url_s,
                        data=body,
                        content_type=content_type,
                        product=product,
                        source_id=site,
                    )
            if imported:
                next_image = {**imported, "source": site, "source_url": url, "status": "ready"}
            else:
                next_image = {
                    "url": url_s,
                    "external_url": url_s,
                    "source": site,
                    "source_url": url,
                    "source_type": "external_hotlink",
                    "role": "gallery",
                    "status": "needs_review",
                    "selected": True,
                    "needs_review": True,
                }
            current_images.append(next_image)
            existing_urls.add(str(next_image.get("url") or "").strip())
            existing_external_urls.update(_media_identity_keys(next_image))
            existing_external_urls.add(url_s)
            source_count += 1
            appended = True
        if appended:
            content["media_images"] = _dedupe_media_items(current_images)
            content.pop("media", None)
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


def _selected_export_stores(provider: str, stores: List[Dict[str, Any]], selected_store_ids: Set[str]) -> List[Dict[str, Any]]:
    enabled_stores = [s for s in stores if bool(s.get("enabled", True))]
    if selected_store_ids:
        selected = [s for s in enabled_stores if str(s.get("id") or "").strip() in selected_store_ids]
        if not selected:
            raise HTTPException(status_code=400, detail=f"No matching stores selected for {provider}")
        return selected
    exportable_stores = [s for s in enabled_stores if s.get("export_enabled", s.get("enabled", True)) is not False]
    enabled = [s for s in exportable_stores if bool(s.get("enabled", True))]
    return enabled or [{"id": "default", "title": "Все магазины"}]


def _effective_provider_category_id(
    category_id: str,
    provider: str,
    mappings: Dict[str, Dict[str, str]],
    parent_by_id: Dict[str, str],
) -> str:
    cur = str(category_id or "").strip()
    seen: Set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        row = mappings.get(cur) if isinstance(mappings.get(cur), dict) else {}
        provider_id = str(row.get(provider) or "").strip()
        if provider_id:
            return provider_id
        cur = parent_by_id.get(cur, "")
    return ""


def _provider_row(rows: List[Dict[str, Any]], provider: str, provider_id: str) -> Optional[Dict[str, Any]]:
    target = str(provider_id or "").strip()
    if not target:
        return None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        prow = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
        if any(str(item.get("id") or "").strip() == target for item in _provider_bindings(prow)):
            return row
    return None


def _provider_bindings(raw: Any) -> List[Dict[str, Any]]:
    cur = raw if isinstance(raw, dict) else {}
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(item: Any) -> None:
        candidate = item if isinstance(item, dict) else {}
        payload = {
            "id": str(candidate.get("id") or "").strip(),
            "name": str(candidate.get("name") or "").strip(),
            "kind": str(candidate.get("kind") or "").strip(),
            "values": list(candidate.get("values") or []) if isinstance(candidate.get("values"), list) else [],
            "required": bool(candidate.get("required") or False),
            "export": bool(candidate.get("export") or False),
        }
        if not payload["id"] and not payload["name"]:
            return
        key = payload["id"] or f"name:{payload['name'].strip().lower()}"
        if key in seen:
            return
        seen.add(key)
        out.append(payload)

    _add(cur)
    for item in cur.get("bindings") if isinstance(cur.get("bindings"), list) else []:
        _add(item)
    return out


def _provider_row_enabled(row: Optional[Dict[str, Any]], provider: str) -> bool:
    if not isinstance(row, dict):
        return False
    pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
    prow = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
    return any(bool(item.get("export")) for item in _provider_bindings(prow))


def _provider_export_binding_count(rows: List[Dict[str, Any]], provider: str) -> int:
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
        prow = pmap.get(provider) if isinstance(pmap.get(provider), dict) else {}
        for binding in _provider_bindings(prow):
            if bool(binding.get("export")) and str(binding.get("id") or "").strip():
                count += 1
    return count


def _store_secret(store: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(store.get(key) or "").strip()
        if value:
            return value
    return ""


async def _hydrate_marketplace_product_content(product_ids: List[str], targets: List[ExportTargetReq], limit: int) -> List[Dict[str, Any]]:
    clean_product_ids = [str(pid or "").strip() for pid in product_ids if str(pid or "").strip()]
    if not clean_product_ids:
        return []
    connectors_state = ConnectorsStateReadAdapter()
    max_items = max(1, min(int(limit or len(clean_product_ids) or 1), len(clean_product_ids)))
    hydrated: List[Dict[str, Any]] = []
    for target in targets or []:
        provider = str(target.provider or "").strip()
        selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
        if provider == "yandex_market":
            stores = _selected_export_stores(provider, connectors_state.import_stores("yandex_market"), selected_store_ids)
            for store in stores:
                token = _store_secret(store, "token", "access_token", "api_key")
                business_id = _store_secret(store, "business_id")
                if not token or not business_id:
                    continue
                try:
                    result = await sync_offer_cards(
                        OfferCardsSyncReq(
                            product_ids=clean_product_ids,
                            limit=max_items,
                            token=token,
                            business_id=business_id,
                            auth_mode=str(store.get("auth_mode") or "auto"),
                            store_id=str(store.get("id") or ""),
                            store_title=str(store.get("title") or ""),
                            include_offer_mappings=True,
                            apply_to_products=True,
                            overwrite_existing=False,
                        )
                    )
                    hydrated.append({"provider": provider, "store_id": str(store.get("id") or ""), "count": int(result.get("count") or 0), "updated_products": int(result.get("updated_products") or 0)})
                except Exception as exc:
                    hydrated.append({"provider": provider, "store_id": str(store.get("id") or ""), "error": str(exc)[:240]})
        elif provider == "ozon":
            stores = _selected_export_stores(provider, connectors_state.import_stores("ozon"), selected_store_ids)
            for store in stores:
                api_key = _store_secret(store, "api_key", "token", "access_token")
                client_id = _store_secret(store, "client_id")
                if not api_key or not client_id:
                    continue
                try:
                    result = await sync_product_statuses(
                        OzonProductsSyncReq(
                            product_ids=clean_product_ids,
                            limit=max_items,
                            token=api_key,
                            client_id=client_id,
                            store_id=str(store.get("id") or ""),
                            store_title=str(store.get("title") or ""),
                        )
                    )
                    hydrated.append({"provider": provider, "store_id": str(store.get("id") or ""), "count": int(result.get("count") or 0), "updated_products": int(result.get("updated_products") or 0)})
                except Exception as exc:
                    hydrated.append({"provider": provider, "store_id": str(store.get("id") or ""), "error": str(exc)[:240]})
    return hydrated


def _infer_ozon_type(product: Dict[str, Any]) -> str:
    title = str(product.get("title") or "").strip().lower()
    category_name = ""
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    for candidate in (product.get("category_name"), content.get("category_name")):
        if str(candidate or "").strip():
            category_name = str(candidate or "").strip().lower()
            break
    haystack = f"{title} {category_name}"
    if "смартфон" in haystack or "iphone" in haystack:
        return "Смартфон"
    if "ноутбук" in haystack or "macbook" in haystack:
        return "Ноутбук"
    if "планшет" in haystack or "ipad" in haystack:
        return "Планшет"
    if "наушник" in haystack or "airpods" in haystack:
        return "Наушники"
    if "умные часы" in haystack or "часы apple watch" in haystack or "apple watch" in haystack or "smart watch" in haystack or "smartwatch" in haystack:
        return "Умные часы"
    if "приставк" in haystack or "телевизор" in haystack:
        return "ТВ-приставка"
    return ""


def _infer_ozon_tnved(product: Dict[str, Any], inferred_type: str) -> Optional[Dict[str, Any]]:
    type_value = str(inferred_type or "").strip().lower()
    title = str(product.get("title") or "").strip().lower()
    category_name = ""
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    for candidate in (product.get("category_name"), content.get("category_name")):
        if str(candidate or "").strip():
            category_name = str(candidate or "").strip().lower()
            break
    haystack = f"{title} {category_name}"
    if type_value == "смартфон" or "смартфон" in haystack or "iphone" in haystack:
        return {"value": "8517130000 - Смартфоны", "dictionary_value_id": 971400011}
    if type_value in {"ноутбук", "планшет"} or "ноутбук" in haystack or "macbook" in haystack or "планшет" in haystack or "ipad" in haystack:
        return {
            "value": "8471300000 - Машины вычислительные портативные массой не более 10 кг, содержащие, по крайней мере, из центрального блока обработки данных, клавиатуры и дисплея",
            "dictionary_value_id": 971399753,
        }
    if type_value == "тв-приставка" or "приставк" in haystack:
        return {
            "value": "8517620009 - Прочие машины для приема, преобразования и передачи или восстановления голоса, изображений или других данных",
            "dictionary_value_id": 971400016,
        }
    return None


def _infer_brand(product: Dict[str, Any]) -> str:
    haystack = f"{product.get('title') or ''} {product.get('brand') or ''}".lower()
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    haystack = f"{haystack} {content.get('brand') or ''}".lower()
    known_brands = [
        ("apple", "Apple"),
        ("samsung", "Samsung"),
        ("xiaomi", "Xiaomi"),
        ("honor", "HONOR"),
        ("huawei", "HUAWEI"),
        ("google", "Google"),
        ("meta", "Meta"),
        ("oculus", "Oculus"),
    ]
    for needle, brand in known_brands:
        if re.search(rf"(^|[^a-zа-я0-9]){re.escape(needle)}([^a-zа-я0-9]|$)", haystack, flags=re.IGNORECASE):
            return brand
    return ""


def _infer_ozon_model_name(product: Dict[str, Any]) -> str:
    raw = str(product.get("title") or "").strip()
    if not raw:
        return ""
    value = re.sub(r"\([^)]*\)", " ", raw)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:смартфон|телефон|мобильный телефон|планшет|ноутбук|наушники|часы|умные часы)\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:apple|samsung|xiaomi|honor|huawei|google|meta|oculus)\s+", "", value, flags=re.IGNORECASE)
    value = re.split(r"\b\d+\s*(?:gb|гб|tb|тб|mb|мб)\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    value = re.sub(r"\b(?:esim|sim|dual|nano|global|ru|eac)\b.*$", "", value, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", value).strip(" -/,")


def _upsert_ozon_attribute(
    attributes: List[Dict[str, Any]],
    attr_id: str,
    name: str,
    value: str,
    source: str,
    dictionary_value_id: Optional[int] = None,
) -> None:
    clean_value = str(value or "").strip()
    if not clean_value:
        return
    target = str(attr_id or "").strip()
    attributes[:] = [attr for attr in attributes if str(attr.get("id") or "").strip() != target]
    value_payload: Dict[str, Any] = {"value": clean_value}
    if dictionary_value_id is not None:
        value_payload["dictionary_value_id"] = int(dictionary_value_id)
    attributes.append(
        {
            "id": target,
            "name": name,
            "values": [value_payload],
            "sourceCatalogName": source,
        }
    )


def _normalize_ozon_category_ref(category_ref: Any) -> str:
    ref = str(category_ref or "").strip()
    if ref.startswith("type:"):
        parts = ref.split(":")
        if len(parts) >= 3 and str(parts[1] or "").strip():
            return str(parts[1] or "").strip()
    return ref


def _ozon_category_store_sources(category_ref: Any) -> Optional[Dict[str, List[str]]]:
    lookup_id = _normalize_ozon_category_ref(category_ref)
    if not lookup_id:
        return None
    doc = read_doc(OZON_CATEGORIES_TREE_PATH, default={})
    flat = doc.get("flat") if isinstance(doc, dict) else []
    if not isinstance(flat, list):
        return None
    for row in flat:
        if not isinstance(row, dict):
            continue
        row_id = str(row.get("id") or "").strip()
        row_category_id = str(row.get("category_id") or "").strip()
        if lookup_id not in {row_id, row_category_id}:
            continue
        sources = {
            "source_store_ids": [
                str(item or "").strip()
                for item in (row.get("source_store_ids") if isinstance(row.get("source_store_ids"), list) else [])
                if str(item or "").strip()
            ],
            "source_titles": [
                str(item or "").strip()
                for item in (row.get("source_titles") if isinstance(row.get("source_titles"), list) else [])
                if str(item or "").strip()
            ],
            "source_client_ids": [
                str(item or "").strip()
                for item in (row.get("source_client_ids") if isinstance(row.get("source_client_ids"), list) else [])
                if str(item or "").strip()
            ],
        }
        if sources["source_store_ids"] or sources["source_client_ids"] or sources["source_titles"]:
            return sources
        return None
    return None


def _ozon_store_supports_category(store: Dict[str, Any], category_ref: Any) -> tuple[bool, str]:
    sources = _ozon_category_store_sources(category_ref)
    if not sources:
        return True, ""
    source_store_ids = {str(item or "").strip() for item in sources.get("source_store_ids") or [] if str(item or "").strip()}
    source_client_ids = {str(item or "").strip() for item in sources.get("source_client_ids") or [] if str(item or "").strip()}
    store_id = str(store.get("id") or "").strip()
    client_id = str(store.get("client_id") or store.get("business_id") or "").strip()
    if (store_id and store_id in source_store_ids) or (client_id and client_id in source_client_ids):
        return True, ""
    store_title = str(store.get("title") or store_id or client_id or "выбранном магазине").strip()
    available = ", ".join(sources.get("source_titles") or []) or "других Ozon-магазинах"
    return False, f"Ozon: категория недоступна в магазине {store_title}. Доступна в: {available}"


def _ozon_export_preview(product_ids: List[str], limit: int) -> Dict[str, Any]:
    ids_filter = {str(x or "").strip() for x in (product_ids or []) if str(x or "").strip()}
    products = query_products_full(ids=sorted(ids_filter)) if ids_filter else _load_products()
    nodes = _load_nodes()
    parent_by_id = _parent_map(nodes)
    mappings = _load_category_mapping()
    attr_rows_by_cid = _load_attr_mapping_rows()
    competitor_db = load_competitor_mapping_db()
    discovery = competitor_db.get("discovery") if isinstance(competitor_db.get("discovery"), dict) else {}

    items: List[Dict[str, Any]] = []
    ready_count = 0
    for product in products:
        pid = str(product.get("id") or "").strip()
        if not pid or (ids_filter and pid not in ids_filter):
            continue
        if len(items) >= int(limit):
            break

        category_id = str(product.get("category_id") or "").strip()
        ozon_category_id = _effective_provider_category_id(category_id, "ozon", mappings, parent_by_id)
        rows = _effective_attr_rows(category_id, attr_rows_by_cid, parent_by_id)
        offer_id = _preferred_offer_id(product)
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        media_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        media_legacy = content.get("media") if isinstance(content.get("media"), list) else []
        media = media_images if media_images else media_legacy
        pictures = _export_media_urls(media)
        status = str(product.get("status") or "").strip()

        type_row = _provider_row(rows, "ozon", "8229")
        brand_row = _provider_row(rows, "ozon", "85")
        model_group_row = _provider_row(rows, "ozon", "9048")
        name_row = _provider_row(rows, "ozon", "4180")
        description_row = _provider_row(rows, "ozon", "4191")
        vendor = _extract_product_value(product, str((brand_row or {}).get("catalog_name") or "Бренд"))
        vendor = vendor or _infer_brand(product)
        name = _extract_product_value(product, str((name_row or {}).get("catalog_name") or "Наименование товара")) or str(product.get("title") or "").strip()
        description = _extract_product_value(product, str((description_row or {}).get("catalog_name") or "Описание товара"))
        type_value = _extract_product_value(product, str((type_row or {}).get("catalog_name") or "Тип"))
        model_group = _extract_product_value(product, str((model_group_row or {}).get("catalog_name") or "Название модели"))
        inferred_type = _infer_ozon_type(product)
        inferred_model_group = _infer_ozon_model_name(product)
        type_value = inferred_type or type_value
        model_group = model_group or inferred_model_group
        tnved = _infer_ozon_tnved(product, type_value)

        attributes: List[Dict[str, Any]] = []
        value_mapping_missing: List[str] = []
        mapped_attribute_values_count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            catalog_name = str(row.get("catalog_name") or "").strip()
            pmap = row.get("provider_map") if isinstance(row.get("provider_map"), dict) else {}
            oz = pmap.get("ozon") if isinstance(pmap.get("ozon"), dict) else {}
            if not isinstance(oz, dict):
                continue
            value = _extract_product_value(product, catalog_name)
            if not value:
                continue
            dict_id = dict_id_for_product_feature(product, catalog_name)
            value_details = provider_export_value_details(dict_id, "ozon", value) if dict_id else {"value": value, "mapped": True}
            value = str(value_details.get("value") or "").strip()
            if not bool(value_details.get("mapped", True)):
                value_mapping_missing.append(catalog_name)
            if not value:
                continue
            for binding in _provider_bindings(oz):
                if not bool(binding.get("export")):
                    continue
                attr_id = str(binding.get("id") or "").strip()
                if not attr_id:
                    continue
                mapped_attribute_values_count += 1
                attributes.append(
                    {
                        "id": attr_id,
                        "name": str(binding.get("name") or row.get("catalog_name") or "").strip(),
                        "values": [{"value": value}],
                        "sourceCatalogName": catalog_name,
                    }
                )
        _upsert_ozon_attribute(attributes, "8229", "Тип", type_value, "Системное поле")
        _upsert_ozon_attribute(attributes, "85", "Бренд", vendor, "Системное поле")
        _upsert_ozon_attribute(attributes, "9048", "Название модели", model_group, "Системное поле")
        if tnved:
            _upsert_ozon_attribute(
                attributes,
                "22232",
                "ТН ВЭД коды ЕАЭС",
                str(tnved.get("value") or ""),
                "Системное поле",
                int(tnved.get("dictionary_value_id")) if tnved.get("dictionary_value_id") is not None else None,
            )

        missing: List[str] = []
        missing_details: List[Dict[str, Any]] = []
        if status in {"archived", "archive"}:
            missing.append("Товар в архиве")
            missing_details.append(_missing_detail("archived_product", "Товар в архиве", "product"))
        if not offer_id:
            missing.append("SKU GT (offer_id) не заполнен")
            missing_details.append(_missing_detail("missing_offer_id", "SKU GT (offer_id) не заполнен", "description"))
        if not ozon_category_id:
            missing.append("Нет сопоставления категории с Ozon")
            missing_details.append(_missing_detail("category_mapping_required", "Нет сопоставления категории с Ozon", "sources"))
        if not name:
            missing.append("Название товара не заполнено")
            missing_details.append(_missing_detail("missing_title", "Название товара не заполнено", "description"))
        if not pictures:
            confirmed_links = _confirmed_links_for_product(discovery, pid)
            if confirmed_links:
                message = "Нет изображений: проверьте медиа товара или повторите загрузку из подтвержденных источников"
                missing.append(message)
                missing_details.append(_missing_detail("media_import_required", message, "media"))
            else:
                message = "Нет изображений: импортируйте фото с площадки; если площадка не вернула медиа, подтвердите карточку конкурента"
                missing.append(message)
                missing_details.append(_missing_detail("marketplace_media_import_required", message, "import"))
        elif _media_review_count(media) > 0:
            message = "Медиа найдено, но часть изображений требует проверки перед выгрузкой"
            missing.append(message)
            missing_details.append(_missing_detail("media_review_required", message, "media", count=_media_review_count(media)))
        if _provider_export_binding_count(rows, "ozon") <= 0:
            message = "Нет сопоставленных PIM-параметров для Ozon: соберите инфо-модель и свяжите параметры площадки"
            missing.append(message)
            missing_details.append(_missing_detail("parameter_mapping_required", message, "params"))
        elif mapped_attribute_values_count <= 0:
            message = "Параметры для Ozon сопоставлены, но у товара нет заполненных значений для выгрузки"
            missing.append(message)
            missing_details.append(_missing_detail("parameter_values_missing", message, "params"))
        if not type_value:
            missing.append("Ozon: обязательный параметр 'Тип' не сопоставлен/пуст")
            missing_details.append(_missing_detail("required_parameter_missing", "Ozon: обязательный параметр 'Тип' не сопоставлен/пуст", "params", parameter="Тип"))
        if not vendor:
            missing.append("Ozon: обязательный параметр 'Бренд' не сопоставлен/пуст")
            missing_details.append(_missing_detail("required_parameter_missing", "Ozon: обязательный параметр 'Бренд' не сопоставлен/пуст", "params", parameter="Бренд"))
        if not model_group:
            missing.append("Ozon: обязательный параметр 'Название модели' не сопоставлен/пуст")
            missing_details.append(_missing_detail("required_parameter_missing", "Ozon: обязательный параметр 'Название модели' не сопоставлен/пуст", "params", parameter="Название модели"))
        if not tnved:
            missing.append("Ozon: обязательный параметр 'ТН ВЭД коды ЕАЭС' не определен")
            missing_details.append(_missing_detail("required_parameter_missing", "Ozon: обязательный параметр 'ТН ВЭД коды ЕАЭС' не определен", "params", parameter="ТН ВЭД коды ЕАЭС"))
        for pname in sorted(set(value_mapping_missing)):
            message = f"{pname}: значение не сопоставлено с Ozon"
            missing.append(message)
            missing_details.append(_missing_detail("value_mapping_required", message, "values", parameter=pname))

        ready = len(missing) == 0
        if ready:
            ready_count += 1

        items.append(
            {
                "product_id": pid,
                "product_title": str(product.get("title") or pid),
                "category_id": category_id,
                "ready": ready,
                "missing": missing,
                "missing_details": missing_details,
                "payload_item": {
                    "offer_id": offer_id,
                    "name": name,
                    "description_category_id": ozon_category_id,
                    "price": OZON_TECHNICAL_EXPORT_PRICE,
                    "price_source": "technical_placeholder",
                    "images": pictures,
                    "attributes": attributes,
                },
            }
        )

    return {
        "ok": True,
        "engine": "ozon_import_products_preview",
        "items": items,
        "count": len(items),
        "ready_count": ready_count,
        "not_ready_count": max(0, len(items) - ready_count),
    }


def _export_batch_from_preview(
    *,
    provider: str,
    store: Dict[str, Any],
    preview: Dict[str, Any],
) -> Dict[str, Any]:
    items = preview.get("items") if isinstance(preview.get("items"), list) else []
    count = int(preview.get("count") or len(items) or 0)
    ready_count = int(preview.get("ready_count") or 0)
    not_ready_count = int(preview.get("not_ready_count") or max(0, count - ready_count))
    blockers: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        missing = item.get("missing") if isinstance(item.get("missing"), list) else []
        missing_clean = [str(x or "").strip() for x in missing if str(x or "").strip()]
        missing_details = item.get("missing_details") if isinstance(item.get("missing_details"), list) else []
        missing_details_clean = [x for x in missing_details if isinstance(x, dict)]
        payload_item = item.get("payload_item") if isinstance(item.get("payload_item"), dict) else {}
        if not missing_clean:
            continue
        offer_id = str(payload_item.get("offerId") or payload_item.get("offer_id") or "").strip()
        product_id = str(item.get("product_id") or "").strip()
        blockers.append(
            {
                "product_id": product_id,
                "offer_id": offer_id,
                "product_title": str(item.get("product_title") or "").strip(),
                "category_id": str(item.get("category_id") or "").strip(),
                "missing": missing_clean,
                "missing_details": missing_details_clean,
            }
        )
    return {
        "provider": provider,
        "store_id": str(store.get("id") or "default"),
        "store_title": str(store.get("title") or "Все магазины"),
        "status": "ready" if not_ready_count == 0 else "blocked",
        "ready_count": ready_count,
        "not_ready_count": not_ready_count,
        "blockers_count": len(blockers),
        "blockers": blockers[:20],
        "count": count,
        "items": items,
    }


def _summarize_export_batches(product_ids: List[str], batches: List[Dict[str, Any]]) -> Dict[str, Any]:
    product_count = len([pid for pid in product_ids if str(pid or "").strip()])
    target_count = len(batches)
    blocked_batches = sum(1 for batch in batches if str(batch.get("status") or "") != "ready")
    ready_batches = max(0, target_count - blocked_batches)
    ready_target_items = sum(int(batch.get("ready_count") or 0) for batch in batches)
    blocked_target_items = sum(int(batch.get("not_ready_count") or 0) for batch in batches)
    blockers_count = sum(int(batch.get("blockers_count") or 0) for batch in batches)
    return {
        "product_count": product_count,
        "target_count": target_count,
        "batch_count": target_count,
        "ready_batches": ready_batches,
        "blocked_batches": blocked_batches,
        "ready_target_items": ready_target_items,
        "blocked_target_items": blocked_target_items,
        "blockers_count": blockers_count,
        "status": "ready" if target_count > 0 and blocked_batches == 0 else "blocked",
    }


def _clean_export_payload_item(provider: str, payload_item: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(payload_item)
    provider_code = str(provider or "").strip()
    if provider_code == "yandex_market":
        for field in ("barcodes", "manuals", "parameterValues", "videos", "deleteParameters"):
            if isinstance(payload.get(field), list) and not payload.get(field):
                payload.pop(field, None)
    return payload


def _build_export_package(run: Dict[str, Any]) -> Dict[str, Any]:
    batches = run.get("batches") if isinstance(run.get("batches"), list) else []
    package_batches: List[Dict[str, Any]] = []
    ready_items_total = 0
    blocked_items_total = 0
    warnings: List[Dict[str, Any]] = []

    for batch in batches:
        if not isinstance(batch, dict):
            continue
        items = batch.get("items") if isinstance(batch.get("items"), list) else []
        ready_items: List[Dict[str, Any]] = []
        blocked_items = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            payload_item = item.get("payload_item") if isinstance(item.get("payload_item"), dict) else {}
            if bool(item.get("ready")) and payload_item:
                payload = _clean_export_payload_item(str(batch.get("provider") or "").strip(), payload_item)
                ready_items.append(
                    {
                        "product_id": str(item.get("product_id") or "").strip(),
                        "offer_id": str(payload.get("offerId") or payload.get("offer_id") or "").strip(),
                        "payload": payload,
                    }
                )
            else:
                blocked_items += 1
        ready_items_total += len(ready_items)
        blocked_items_total += blocked_items
        if blocked_items:
            warnings.append(
                {
                    "provider": str(batch.get("provider") or "").strip(),
                    "store_id": str(batch.get("store_id") or "").strip(),
                    "store_title": str(batch.get("store_title") or "").strip(),
                    "blocked_items": blocked_items,
                }
            )
        package_batches.append(
            {
                "provider": str(batch.get("provider") or "").strip(),
                "store_id": str(batch.get("store_id") or "").strip(),
                "store_title": str(batch.get("store_title") or "").strip(),
                "status": "ready" if blocked_items == 0 else "partial",
                "ready_count": len(ready_items),
                "blocked_count": blocked_items,
                "items": ready_items,
            }
        )

    status = "ready" if package_batches and blocked_items_total == 0 else "partial"
    return {
        "version": 1,
        "run_id": str(run.get("id") or run.get("run_id") or "").strip(),
        "created_at": _now_iso(),
        "selection": run.get("selection") if isinstance(run.get("selection"), dict) else {},
        "targets": run.get("targets") if isinstance(run.get("targets"), list) else [],
        "status": status,
        "summary": {
            "batch_count": len(package_batches),
            "ready_items": ready_items_total,
            "blocked_items": blocked_items_total,
            "warnings_count": len(warnings),
        },
        "warnings": warnings,
        "batches": package_batches,
    }


def _selection_key(node_ids: List[str], product_ids: List[str], include_descendants: bool, limit: int) -> str:
    return "|".join(
        [
            ",".join(sorted({str(x or "").strip() for x in node_ids if str(x or "").strip()})),
            ",".join(sorted({str(x or "").strip() for x in product_ids if str(x or "").strip()})),
            "1" if include_descendants else "0",
            str(int(limit)),
        ]
    )


def _export_request_key(req: CatalogExportRunReq) -> str:
    target_parts: List[str] = []
    for target in req.targets or []:
        provider = str(target.provider or "").strip()
        stores = ",".join(sorted({str(item or "").strip() for item in target.store_ids if str(item or "").strip()}))
        if provider:
            target_parts.append(f"{provider}:{stores}")
    selection_key = _selection_key(
        req.selection.node_ids,
        req.selection.product_ids,
        bool(req.selection.include_descendants),
        int(req.limit),
    )
    return f"{selection_key}|targets={'/'.join(sorted(target_parts))}"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    return _backend_root().parent


def _save_export_job(job: Dict[str, Any]) -> Dict[str, Any]:
    upsert_pim_workflow_run(job, workflow=_EXPORT_WORKFLOW)
    return job


def _claim_export_job(job_id: str) -> Optional[Dict[str, Any]]:
    return claim_pim_workflow_run_as_running(
        job_id,
        workflow=_EXPORT_WORKFLOW,
        payload_updates={
            "phase": "preparing",
            "message": "Готовлю export batch: проверяю медиа, описание, категории, параметры и значения.",
            "started_at": _now_iso(),
            "updated_ts": time.time(),
        },
    )


def _prune_export_jobs() -> None:
    now = time.time()
    for job in list_pim_workflow_runs(workflow=_EXPORT_WORKFLOW, statuses=["queued", "running"], limit=200):
        updated = float(job.get("updated_ts") or job.get("created_ts") or 0.0)
        if updated and now - updated > _EXPORT_JOB_TTL_SECONDS:
            job.update({
                "status": "failed",
                "phase": "stale",
                "message": "Подготовка экспорта была прервана. Запустите проверку заново.",
                "finished_at": _now_iso(),
                "updated_ts": now,
                "error": "STALE_EXPORT_JOB",
            })
            _save_export_job(job)


def _public_export_job(job: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ok": True,
        "job_id": str(job.get("job_id") or job.get("id") or ""),
        "run_id": str(job.get("run_id") or ""),
        "status": str(job.get("status") or "queued"),
        "phase": str(job.get("phase") or ""),
        "message": str(job.get("message") or ""),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "summary": job.get("summary"),
        "error": job.get("error") or "",
        "run": job.get("run") if isinstance(job.get("run"), dict) else None,
    }


def _start_export_worker_process(job_id: str, organization_id: Optional[str]) -> None:
    env = os.environ.copy()
    backend_root = str(_backend_root())
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = backend_root if not existing_pythonpath else f"{backend_root}{os.pathsep}{existing_pythonpath}"
    command = [
        sys.executable,
        "-m",
        "app.workers.catalog_export_prepare",
        "--job-id",
        job_id,
    ]
    if organization_id:
        command.extend(["--organization-id", organization_id])
    subprocess.Popen(
        command,
        cwd=str(_repo_root()),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _build_import_overview_payload(
    node_ids: List[str],
    product_ids: List[str],
    include_descendants: bool,
    limit: int,
) -> Dict[str, Any]:
    products = _resolve_products(node_ids, product_ids, include_descendants, limit=int(limit))
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
    _remember_import_overview(cache_key, payload)
    return payload


@router.post("/import/run")
async def run_catalog_import(req: CatalogImportRunReq) -> Dict[str, Any]:
    _import_overview_cache.clear()
    products = _resolve_products(req.selection.node_ids, req.selection.product_ids, bool(req.selection.include_descendants), limit=int(req.limit))
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
    sibling_updates = _hydrate_missing_content_from_variant_siblings(
        [product_map[pid] for pid in target_product_ids if isinstance(product_map.get(pid), dict)]
    )
    for product in sibling_updates:
        product_id = str(product.get("id") or "").strip()
        if product_id:
            product_map[product_id] = product
            total_changed_ids.add(product_id)

    product_summaries: List[Dict[str, Any]] = []
    conflicts: List[Dict[str, Any]] = []

    for product_id in target_product_ids:
        product = product_map.get(product_id)
        if not isinstance(product, dict):
            continue
        template_id = _resolve_template_id(str(product.get("category_id") or "").strip(), nodes)
        links_by_site = _product_partner_links_by_site(product, competitor_db)
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
                    raw_result = await _extract_competitor_content_with_retry(url, attempts=3 if site == "store77" else 2)
                except Exception as e:
                    competitor_results[site] = {"ok": False, "error": str(e) or "EXTRACT_FAILED", "url": url}
                    continue
                specs = raw_result.get("specs") if isinstance(raw_result.get("specs"), dict) else {}
                explicit_mapping = mapping_by_site.get(site) if isinstance(mapping_by_site.get(site), dict) else {}
                mapped_raw = _auto_map_competitor_specs(template_id, specs, explicit_mapping)
                ai_mapped = await _ai_map_competitor_specs_to_template(template_id, site, specs)
                for code, value in ai_mapped.items():
                    mapped_raw.setdefault(code, value)
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
                changed, field_conflicts, _ = await _apply_competitor_result_to_product(product, template_id, site, url, comp_payload)
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
        _save_products([product for product in products_doc if str(product.get("id") or "").strip() in total_changed_ids])

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
            "sibling_hydrated_products": len(sibling_updates),
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
        "sibling_hydrated_products": len(sibling_updates),
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
        _save_products([product for product in products if str(product.get("id") or "").strip() in changed_ids])
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


def _build_catalog_export_run(req: CatalogExportRunReq) -> Dict[str, Any]:
    products = _resolve_products(req.selection.node_ids, req.selection.product_ids, bool(req.selection.include_descendants), limit=int(req.limit))
    products = products[: int(req.limit)]
    product_ids = [str(p.get("id") or "").strip() for p in products if str(p.get("id") or "").strip()]
    enriched_from_candidates: List[str] = []
    if product_ids:
        enriched_from_candidates = sorted(asyncio.run(_enrich_export_products_from_candidate_media(products)))
    marketplace_hydration: List[Dict[str, Any]] = []
    if product_ids:
        marketplace_hydration = asyncio.run(_hydrate_marketplace_product_content(product_ids, req.targets or [], int(req.limit)))
        sibling_updates = _hydrate_missing_content_from_variant_siblings(query_products_full(ids=product_ids))
        if sibling_updates:
            _save_products(sibling_updates)
            marketplace_hydration.append({"provider": "variant_sibling", "updated_products": len(sibling_updates), "count": len(sibling_updates)})
    connectors_state = ConnectorsStateReadAdapter()
    batches: List[Dict[str, Any]] = []
    for target in req.targets or []:
        provider = str(target.provider or "").strip()
        if provider == "yandex_market":
            preview = yandex_export_preview(ExportPreviewReq(product_ids=product_ids, only_active=False, limit=len(product_ids) or 1000))
            stores = connectors_state.import_stores("yandex_market")
            selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
            selected_stores = _selected_export_stores(provider, stores, selected_store_ids)
            for store in selected_stores:
                batches.append(_export_batch_from_preview(provider=provider, store=store, preview=preview))
        elif provider == "ozon":
            stores = connectors_state.import_stores("ozon")
            selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
            selected_stores = _selected_export_stores(provider, stores, selected_store_ids)
            preview = _ozon_export_preview(product_ids, len(product_ids) or 1000)
            for store in selected_stores:
                batches.append(_export_batch_from_preview(provider=provider, store=store, preview=preview))
    run_id = f"export_{uuid4().hex[:10]}"
    summary = _summarize_export_batches(product_ids, batches)
    runs = _load_runs(EXPORT_RUNS_PATH)
    runs["runs"][run_id] = {
        "id": run_id,
        "created_at": _now_iso(),
        "selection": req.selection.model_dump(),
        "targets": [t.model_dump() for t in req.targets or []],
        "summary": summary,
        "batches": batches,
        "enriched_from_candidates": enriched_from_candidates,
        "marketplace_hydration": marketplace_hydration,
    }
    _save_runs(EXPORT_RUNS_PATH, runs)
    return {"ok": True, "run_id": run_id, "count": len(product_ids), "summary": summary, "batches": batches, "enriched_from_candidates": enriched_from_candidates, "marketplace_hydration": marketplace_hydration}


@router.post("/export/run")
def run_catalog_export(req: CatalogExportRunReq) -> Dict[str, Any]:
    return _build_catalog_export_run(req)


def _run_catalog_export_job(job_id: str) -> None:
    job = get_pim_workflow_run(job_id, workflow=_EXPORT_WORKFLOW)
    if not isinstance(job, dict):
        return
    request_payload = job.get("request") if isinstance(job.get("request"), dict) else {}
    try:
        req = CatalogExportRunReq.model_validate(request_payload)
    except Exception as exc:
        job.update({
            "status": "failed",
            "phase": "failed",
            "message": "Не удалось прочитать параметры export batch.",
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "error": f"{exc.__class__.__name__}: {str(exc).strip()}"[:500],
        })
        _save_export_job(job)
        return

    job.update({
        "status": "running",
        "phase": "preparing",
        "message": "Готовлю export batch: проверяю медиа, описание, категории, параметры и значения.",
        "started_at": job.get("started_at") or _now_iso(),
        "updated_ts": time.time(),
    })
    _save_export_job(job)
    try:
        result = _build_catalog_export_run(req)
        job.update({
            "status": "completed",
            "phase": "completed",
            "message": "Export batch подготовлен. Проверьте готовые строки и блокеры.",
            "run_id": result.get("run_id"),
            "run": result,
            "summary": result.get("summary"),
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
        })
        _save_export_job(job)
    except Exception as exc:
        job.update({
            "status": "failed",
            "phase": "failed",
            "message": "Подготовка export batch не завершилась. Можно запустить проверку заново.",
            "finished_at": _now_iso(),
            "updated_ts": time.time(),
            "error": f"{exc.__class__.__name__}: {str(exc).strip()}"[:500],
        })
        _save_export_job(job)


@router.post("/export/jobs")
def start_catalog_export_job(req: CatalogExportRunReq) -> Dict[str, Any]:
    _prune_export_jobs()
    request_key = _export_request_key(req)
    for job in list_pim_workflow_runs(workflow=_EXPORT_WORKFLOW, statuses=["queued", "running"], limit=100):
        if str(job.get("request_key") or "") == request_key:
            return _public_export_job(job)

    job_id = f"export_job_{uuid4().hex}"
    job = {
        "id": job_id,
        "run_id": "",
        "job_id": job_id,
        "workflow": _EXPORT_WORKFLOW,
        "status": "queued",
        "phase": "queued",
        "message": "Подготовка экспорта поставлена в очередь.",
        "request": req.model_dump(),
        "request_key": request_key,
        "created_at": _now_iso(),
        "created_ts": time.time(),
        "updated_ts": time.time(),
    }
    _save_export_job(job)
    organization_id = str(current_tenant_organization_id() or "").strip() or "org_default"
    _start_export_worker_process(job_id, organization_id)
    return _public_export_job(job)


@router.get("/export/jobs/{job_id}")
def get_catalog_export_job(job_id: str) -> Dict[str, Any]:
    _prune_export_jobs()
    jid = str(job_id or "").strip()
    job = get_pim_workflow_run(jid, workflow=_EXPORT_WORKFLOW)
    if not isinstance(job, dict):
        raise HTTPException(status_code=404, detail="EXPORT_JOB_NOT_FOUND")
    return _public_export_job(job)


@router.get("/export/runs/{run_id}")
def get_catalog_export_run(run_id: str) -> Dict[str, Any]:
    runs = _load_runs(EXPORT_RUNS_PATH)
    row = (runs.get("runs") or {}).get(run_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return {"ok": True, "run": row}


@router.get("/export/runs/{run_id}/package")
def get_catalog_export_package(run_id: str) -> Dict[str, Any]:
    runs = _load_runs(EXPORT_RUNS_PATH)
    row = (runs.get("runs") or {}).get(run_id)
    if not isinstance(row, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return {"ok": True, "package": _build_export_package(row)}


@router.get("/export/latest-run")
def get_latest_catalog_export_run(
    category_id: str = Query(default=""),
    product_id: str = Query(default=""),
) -> Dict[str, Any]:
    category = str(category_id).strip() if isinstance(category_id, str) else ""
    product = str(product_id).strip() if isinstance(product_id, str) else ""
    runs = _load_runs(EXPORT_RUNS_PATH)
    rows = [row for row in (runs.get("runs") or {}).values() if isinstance(row, dict)]

    def matches(row: Dict[str, Any]) -> bool:
        selection = row.get("selection") if isinstance(row.get("selection"), dict) else {}
        node_ids = {str(item or "").strip() for item in selection.get("node_ids") or [] if str(item or "").strip()}
        product_ids = {str(item or "").strip() for item in selection.get("product_ids") or [] if str(item or "").strip()}
        if category and category not in node_ids:
            return False
        if product and product not in product_ids:
            return False
        return True

    filtered = [row for row in rows if matches(row)]
    latest = max(filtered, key=lambda row: str(row.get("created_at") or row.get("id") or ""), default=None)
    if not latest:
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    return {"ok": True, "run": latest}
