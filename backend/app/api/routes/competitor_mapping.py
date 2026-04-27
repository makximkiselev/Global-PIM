# backend/app/api/routes/competitor_mapping.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import html as html_lib
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

import httpx

from fastapi import APIRouter, HTTPException

from app.core.tenant_context import (
    current_tenant_organization_id,
    reset_current_tenant_organization_id,
    set_current_tenant_organization_id,
)
from app.core.competitors.browser_fetch import fetch_html as fetch_browser_html
from app.storage.json_store import (
    load_competitor_mapping_db,
    load_dictionaries_db,
    save_competitor_mapping_db,
    load_templates_db,
)
from app.storage.relational_pim_store import query_products_full, upsert_product_item
from app.core.value_mapping import canonicalize_dictionary_value

# ✅ Реальный извлекатель полей конкурента (Playwright + restore/store77 парсеры)
from app.core.competitors.extract_competitor_fields import (
    extract_competitor_fields,
    extract_competitor_content,
)

router = APIRouter(prefix="/competitor-mapping", tags=["competitor-mapping"])

_BOOTSTRAP_CACHE_TTL_SECONDS = 300.0
_DISCOVERY_SOURCE_TIMEOUT_SECONDS = 32.0
_bootstrap_cache: Dict[str, Dict[str, Any]] = {}
_discovery_run_cache: Dict[str, Dict[str, Any]] = {}


# =========================
# helpers
# =========================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key() -> str:
    return str(current_tenant_organization_id() or "org_default").strip() or "org_default"


def _bootstrap_cache_entry() -> Dict[str, Any]:
    return _bootstrap_cache.setdefault(_cache_key(), {"at": 0.0, "payload": None})


ALLOWED_SITES: Dict[str, set[str]] = {
    "restore": {"re-store.ru"},
    "store77": {"store77.net"},
}

DISCOVERY_SOURCES: List[Dict[str, Any]] = [
    {
        "id": "restore",
        "name": "re-store",
        "domain": "re-store.ru",
        "base_url": "https://re-store.ru",
        "status": "active",
        "parser_strategy": "restore",
        "rate_limit": "bounded",
    },
    {
        "id": "store77",
        "name": "store77",
        "domain": "store77.net",
        "base_url": "https://store77.net",
        "status": "active",
        "parser_strategy": "store77",
        "rate_limit": "bounded",
    },
]


def detect_site(url: str) -> Optional[str]:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]

    for site, domains in ALLOWED_SITES.items():
        if host in domains or any(host.endswith("." + d) for d in domains):
            return site
    return None


def _validate_links_keep_keys(links: Any) -> Dict[str, str]:
    """
    Возвращает нормализованные ссылки, проверяя домены.
    ✅ Ключи всегда присутствуют: restore/store77.
    ✅ Пустые значения допускаем и сохраняем как "".
    """
    out: Dict[str, str] = {k: "" for k in ALLOWED_SITES.keys()}
    links = links or {}

    if not isinstance(links, dict):
        raise HTTPException(status_code=400, detail="links must be an object")

    # запретим неизвестные ключи
    for k in links.keys():
        if k not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail=f"Unknown site key: {k}")

    for k in out.keys():
        v = links.get(k)
        url = (str(v).strip() if v is not None else "")
        if not url:
            out[k] = ""
            continue

        site = detect_site(url)
        if site != k:
            raise HTTPException(
                status_code=400,
                detail="Парсинг запрещён: ссылка не из разрешённых сайтов",
            )

        out[k] = url

    return out


def _source_by_id(source_id: str) -> Dict[str, Any]:
    sid = str(source_id or "").strip()
    for source in DISCOVERY_SOURCES:
        if source["id"] == sid:
            return dict(source)
    raise HTTPException(status_code=400, detail=f"Unknown competitor source: {sid}")


def _ensure_discovery_doc(db: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(db, dict):
        db = {"version": 2, "categories": {}, "templates": {}}
    discovery = db.setdefault("discovery", {})
    if not isinstance(discovery, dict):
        discovery = {}
        db["discovery"] = discovery
    for key in ("candidates", "links", "runs"):
        if not isinstance(discovery.get(key), dict):
            discovery[key] = {}
    return discovery


def _candidate_id(product_id: str, source_id: str, url: str) -> str:
    raw = f"{product_id}|{source_id}|{url}".encode("utf-8")
    return "cand_" + hashlib.sha1(raw).hexdigest()[:16]


def _run_id() -> str:
    return "run_" + hashlib.sha1(now_iso().encode("utf-8")).hexdigest()[:16]


def _run_payload(
    run_id: str,
    *,
    status: str,
    sources: List[Dict[str, Any]],
    product_ids: Optional[List[str]],
    limit: int,
    started_at: Optional[str] = None,
    finished_at: Optional[str] = None,
    created_count: int = 0,
    updated_count: int = 0,
    errors: Optional[List[Dict[str, Any]]] = None,
    scanned_products_count: int = 0,
) -> Dict[str, Any]:
    errors = errors or []
    return {
        "id": run_id,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "sources": [source["id"] for source in sources],
        "requested_product_ids": [str(item or "").strip() for item in (product_ids or []) if str(item or "").strip()],
        "limit": max(1, int(limit or 1)),
        "scanned_products_count": scanned_products_count,
        "created_count": created_count,
        "updated_count": updated_count,
        "errors_count": len(errors),
        "errors": errors,
    }


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    return _backend_root().parent


def _start_discovery_worker_process(run_id: str, organization_id: Optional[str]) -> None:
    env = os.environ.copy()
    backend_root = str(_backend_root())
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = backend_root if not existing_pythonpath else f"{backend_root}{os.pathsep}{existing_pythonpath}"
    env.setdefault("ENABLE_HTTP_COMPETITOR_DISCOVERY", "0")
    env.setdefault("ENABLE_BROWSER_COMPETITOR_DISCOVERY", "1")

    command = [
        sys.executable,
        "-m",
        "app.workers.competitor_discovery_run",
        "--run-id",
        run_id,
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


def _remember_discovery_run(run: Dict[str, Any]) -> Dict[str, Any]:
    run_id = str(run.get("id") or "").strip()
    if run_id:
        _discovery_run_cache[run_id] = dict(run)
    return run


def _normalize_candidate(product: Dict[str, Any], source: Dict[str, Any], raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url") or "").strip()
    if not url:
        return None
    source_id = str(source.get("id") or "").strip()
    if detect_site(url) != source_id:
        return None
    product_id = str(product.get("id") or "").strip()
    if not product_id:
        return None
    score_raw = raw.get("confidence_score", 0)
    try:
        score = max(0.0, min(1.0, float(score_raw)))
    except Exception:
        score = 0.0
    reasons = raw.get("confidence_reasons")
    if not isinstance(reasons, list):
        reasons = []
    return {
        "id": _candidate_id(product_id, source_id, url),
        "product_id": product_id,
        "product_title": str(product.get("title") or "").strip(),
        "product_sku": str(product.get("sku_gt") or product.get("sku_pim") or "").strip(),
        "category_id": str(product.get("category_id") or "").strip(),
        "source_id": source_id,
        "source_name": str(source.get("name") or source_id),
        "url": url,
        "normalized_url": url,
        "title": str(raw.get("title") or "").strip(),
        "match_group_key": str(raw.get("match_group_key") or _model_memory_color_group_key(raw.get("title") or product.get("title"))),
        "product_sim_profile": _sim_profile(product.get("title")),
        "candidate_sim_profile": _sim_profile(raw.get("title")),
        "brand": str(raw.get("brand") or "").strip(),
        "model": str(raw.get("model") or "").strip(),
        "sku": str(raw.get("sku") or "").strip(),
        "gtin": str(raw.get("gtin") or "").strip(),
        "price": raw.get("price"),
        "availability": str(raw.get("availability") or "").strip(),
        "image_url": str(raw.get("image_url") or "").strip(),
        "confidence_score": score,
        "confidence_reasons": [str(item) for item in reasons if str(item or "").strip()],
        "status": "needs_review",
        "first_seen_at": now_iso(),
        "last_seen_at": now_iso(),
    }


def _discovery_products(product_ids: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
    ids = [str(item or "").strip() for item in (product_ids or []) if str(item or "").strip()]
    products = query_products_full(ids=ids) if ids else query_products_full()
    items = [item for item in products if isinstance(item, dict)]
    # Synchronous discovery is intentionally small to avoid gateway timeouts.
    # Larger crawls must run as background jobs.
    return items[: max(1, min(int(limit or 3), 3))]


async def _discover_product_candidates_for_source(product: Dict[str, Any], source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extension point for real site discovery.

    Site-specific search crawling returns candidate product URLs with evidence.
    """
    source_id = str(source.get("id") or "").strip()
    if source_id == "restore":
        return await _discover_restore_candidates(product)
    if source_id == "store77":
        return await _discover_store77_candidates(product)
    return []


def _query_terms_for_product(product: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    title = str(product.get("title") or "").strip()
    if title:
        compact = re.sub(r"\s+", " ", title)
        if compact and compact not in terms:
            terms.append(compact)
        search_title = re.sub(r"\b(смартфон|телефон)\b", " ", compact, flags=re.I)
        search_title = re.sub(r"\((global|ru|россия)\)", " ", search_title, flags=re.I)
        search_title = re.sub(r"\s+", " ", search_title).strip()
        if search_title and search_title not in terms:
            terms.append(search_title)
    for key in ("sku_gt", "sku_pim"):
        value = str(product.get(key) or "").strip()
        if value and value not in terms:
            terms.append(value)
    return terms[:4]


def _norm_match_text(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", str(value or "").lower()).strip()


_KNOWN_BRAND_TOKENS = {
    "apple",
    "iphone",
    "ipad",
    "macbook",
    "xiaomi",
    "samsung",
    "honor",
    "huawei",
    "realme",
    "oppo",
    "vivo",
    "sony",
    "dyson",
}

_MATCH_REQUIRED_TOKENS = {
    "apple",
    "iphone",
    "ipad",
    "macbook",
    "xiaomi",
    "samsung",
    "honor",
    "huawei",
    "realme",
    "oppo",
    "vivo",
    "sony",
    "dyson",
    "pro",
    "max",
    "plus",
    "ultra",
    "mini",
    "air",
    "esim",
    "sim",
    "2sim",
    "silver",
    "black",
    "white",
    "blue",
    "green",
    "orange",
}

_MATCH_STOP_TOKENS = {
    "смартфон",
    "телефон",
    "global",
    "new",
    "новый",
}


def _brand_tokens(value: Any) -> set[str]:
    normalized = _norm_match_text(value)
    return {token for token in normalized.split() if token in _KNOWN_BRAND_TOKENS}


def _match_tokens(value: Any) -> set[str]:
    normalized = _norm_match_text(value)
    raw_tokens = [token for token in normalized.split() if token and token not in _MATCH_STOP_TOKENS]
    out: set[str] = set()
    idx = 0
    while idx < len(raw_tokens):
        token = raw_tokens[idx]
        next_token = raw_tokens[idx + 1] if idx + 1 < len(raw_tokens) else ""
        if token.isdigit() and next_token in {"gb", "гб", "tb", "тб"}:
            out.add(f"{token}{'gb' if next_token in {'gb', 'гб'} else 'tb'}")
            idx += 2
            continue
        if re.fullmatch(r"\d+(gb|гб)", token):
            out.add(token[:-2] + "gb")
        elif re.fullmatch(r"\d+(tb|тб)", token):
            out.add(token[:-2] + "tb")
        else:
            out.add(token)
        idx += 1
    return out


def _sim_profile(value: Any) -> str:
    normalized = _norm_match_text(value)
    if not normalized:
        return "unknown"
    has_esim = "esim" in normalized or "e sim" in normalized
    has_nano = "nano sim" in normalized or "nanosim" in normalized or "nano" in normalized
    has_dual = (
        "dual sim" in normalized
        or "2sim" in normalized
        or "2 sim" in normalized
        or "две sim" in normalized
        or "две сим" in normalized
        or "две nano" in normalized
    )
    if has_dual:
        return "dual_sim"
    if has_nano and has_esim:
        return "nano_sim_esim"
    if has_esim:
        return "esim_only"
    if has_nano or "sim" in normalized or "сим" in normalized:
        return "physical_sim"
    return "unknown"


def _model_memory_color_group_key(value: Any) -> str:
    normalized = _norm_match_text(value)
    model_match = re.search(r"\biphone\s+(\d{1,2})(?:\s+(pro\s+max|pro|plus|mini))?", normalized)
    memory_match = re.search(r"\b(\d+)\s*(gb|гб|tb|тб)\b", normalized)
    model = ""
    if model_match:
        generation = model_match.group(1)
        suffix = re.sub(r"\s+", "_", (model_match.group(2) or "").strip())
        model = "_".join(part for part in ("iphone", generation, suffix) if part)
    memory = ""
    if memory_match:
        memory = f"{memory_match.group(1)}{'tb' if memory_match.group(2) in {'tb', 'тб'} else 'gb'}"
    color = ""
    color_options = [
        ("natural_titanium", ("natural titanium", "натуральный титан")),
        ("desert_titanium", ("desert titanium", "пустынный титан")),
        ("black_titanium", ("black titanium", "черный титан", "чёрный титан")),
        ("white_titanium", ("white titanium", "белый титан")),
    ]
    raw_lower = str(value or "").lower()
    for slug, aliases in color_options:
        if any(alias in raw_lower or alias in normalized for alias in aliases):
            color = slug
            break
    return "|".join(part for part in (model, memory, color) if part)


def _required_match_tokens(product: Dict[str, Any]) -> set[str]:
    tokens = _match_tokens(product.get("title"))
    required = {token for token in tokens if token in _MATCH_REQUIRED_TOKENS}
    required.update(token for token in tokens if re.fullmatch(r"\d+(gb|tb)", token))
    if "esim" in tokens:
        # Store77 often names the same iPhone variant as "eSim" on listing
        # cards while full specs contain the exact nanoSIM+eSIM detail.
        # Requiring the generic "sim" token here drops valid candidates before
        # content-manager review.
        required.discard("sim")
    if "iphone" in tokens:
        required.update(token for token in tokens if re.fullmatch(r"\d{1,2}", token))
    return required


def _confidence_for_candidate(product: Dict[str, Any], title: str, sku: str, brand: str = "") -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    product_sim = _sim_profile(product.get("title"))
    candidate_sim = _sim_profile(title)
    if product_sim != "unknown" and candidate_sim != "unknown" and product_sim != candidate_sim:
        return 0.0, [f"конфликт SIM: PIM={product_sim}, candidate={candidate_sim}"]
    product_sku = str(product.get("sku_gt") or product.get("sku_pim") or "").strip()
    if product_sku and sku and product_sku.lower() == sku.lower():
        score += 0.25
        reasons.append("SKU совпал")
    product_title = _norm_match_text(product.get("title"))
    candidate_title = _norm_match_text(title)
    product_brand_tokens = _brand_tokens(product.get("title"))
    candidate_brand_tokens = _brand_tokens(brand) | _brand_tokens(title)
    if product_brand_tokens and candidate_brand_tokens and product_brand_tokens.isdisjoint(candidate_brand_tokens):
        return 0.0, ["конфликт бренда"]
    required_tokens = _required_match_tokens(product)
    candidate_tokens = _match_tokens(f"{brand} {title}")
    missing_required = sorted(required_tokens - candidate_tokens)
    if missing_required:
        return 0.0, [f"нет обязательных токенов: {', '.join(missing_required)}"]
    if required_tokens:
        score += 0.58
        reasons.append("обязательные токены совпали")
    if product_title and candidate_title:
        product_tokens = {token for token in _match_tokens(product_title) if len(token) > 1}
        if product_tokens:
            overlap = len(product_tokens & candidate_tokens) / max(1, len(product_tokens))
            if overlap >= 0.6:
                reasons.append(f"название похоже на {round(overlap * 100)}%")
            score += min(0.37, overlap * 0.37)
    return min(1.0, score), reasons or ["найдено в разрешенной выдаче источника"]


def _source_value_key(value: Any) -> str:
    return re.sub(r"[^a-zа-я0-9]+", " ", str(value or "").lower()).strip()


def _confirmed_links_for_product(discovery: Dict[str, Any], product_id: str) -> List[Dict[str, Any]]:
    normalized_product_id = str(product_id or "").strip()
    out: List[Dict[str, Any]] = []
    for link in (discovery.get("links") or {}).values():
        if not isinstance(link, dict):
            continue
        if str(link.get("product_id") or "").strip() != normalized_product_id:
            continue
        if str(link.get("status") or "").strip() != "confirmed":
            continue
        source_id = str(link.get("source_id") or "").strip()
        url = str(link.get("url") or "").strip()
        if source_id in ALLOWED_SITES and url and detect_site(url) == source_id:
            out.append({**link, "source_id": source_id, "url": url})
    return out


def _merge_competitor_content_into_product(
    product: Dict[str, Any],
    *,
    extracted: Dict[str, Dict[str, Any]],
    links: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features_raw = content.get("features") if isinstance(content.get("features"), list) else []
    features: List[Dict[str, Any]] = [dict(item) for item in features_raw if isinstance(item, dict)]

    feature_by_key: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        for key in (feature.get("code"), feature.get("name")):
            normalized = _source_value_key(key)
            if normalized:
                feature_by_key[normalized] = feature

    source_evidence = content.get("source_evidence") if isinstance(content.get("source_evidence"), dict) else {}
    competitors_evidence = source_evidence.get("competitors") if isinstance(source_evidence.get("competitors"), dict) else {}

    matched_count = 0
    unmatched_count = 0
    enriched_sources: List[str] = []

    for source_id, result in extracted.items():
        if not isinstance(result, dict) or not result.get("ok"):
            continue
        enriched_sources.append(source_id)
        specs = result.get("specs") if isinstance(result.get("specs"), dict) else {}
        matched_specs: Dict[str, Any] = {}
        unmatched_specs: Dict[str, Any] = {}

        for spec_name, raw_value in specs.items():
            normalized_name = _source_value_key(spec_name)
            raw_text = str(raw_value or "").strip()
            if not normalized_name or not raw_text:
                continue
            feature = feature_by_key.get(normalized_name)
            if not feature:
                unmatched_specs[str(spec_name)] = raw_text
                unmatched_count += 1
                continue

            source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
            competitor_values = source_values.get("competitor") if isinstance(source_values.get("competitor"), dict) else {}
            competitor_values[source_id] = {
                "raw_value": raw_text,
                "resolved_value": raw_text,
                "canonical_value": str(feature.get("value") or "").strip(),
            }
            source_values["competitor"] = competitor_values
            feature["source_values"] = source_values
            matched_specs[str(spec_name)] = raw_text
            matched_count += 1

        competitors_evidence[source_id] = {
            "source_id": source_id,
            "url": str((links.get(source_id) or {}).get("url") or "").strip(),
            "extracted_at": now_iso(),
            "images": result.get("images") if isinstance(result.get("images"), list) else [],
            "description": str(result.get("description") or "").strip(),
            "matched_specs": matched_specs,
            "unmatched_specs": unmatched_specs,
        }

    content["features"] = features
    source_evidence["competitors"] = competitors_evidence
    content["source_evidence"] = source_evidence
    product["content"] = content
    return {
        "product": product,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "enriched_sources": enriched_sources,
    }


def _extract_restore_search_candidates(html: str, product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not html:
        return []
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r'\\"name\\"\s*:\s*\\"(?P<title>.*?)(?<!\\)\\".*?'
        r'(?:\\"price\\"\s*:\s*\\"(?P<price>.*?)\\".*?)?'
        r'(?:\\"brand\\"\s*:\s*\\"(?P<brand>.*?)\\".*?)?'
        r'(?:\\"skuCode\\"\s*:\s*\\"(?P<sku>.*?)\\".*?)?'
        r'\\"link\\"\s*:\s*\\"(?P<link>/catalog/[^"\\]+/?)\\"',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        link = html_lib.unescape(match.group("link") or "").strip()
        url = urljoin("https://re-store.ru", link)
        if detect_site(url) != "restore" or url in seen:
            continue
        seen.add(url)
        title = html_lib.unescape(match.group("title") or "").strip()
        sku = html_lib.unescape(match.group("sku") or "").strip()
        brand = html_lib.unescape(match.group("brand") or "").strip()
        confidence_score, reasons = _confidence_for_candidate(product, title, sku, brand)
        if confidence_score < 0.78:
            continue
        candidates.append(
            {
                "url": url,
                "title": title,
                "brand": brand,
                "sku": sku,
                "price": match.group("price"),
                "confidence_score": confidence_score,
                "confidence_reasons": reasons,
            }
        )
        if len(candidates) >= 5:
            break
    return candidates


async def _fetch_search_html(url: str) -> str:
    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        },
        timeout=6.0,
        follow_redirects=True,
        verify=False,
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def _discover_restore_candidates(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if os.getenv("ENABLE_HTTP_COMPETITOR_DISCOVERY", "").strip().lower() not in {"1", "true", "yes"}:
        # External crawling must not run in the web API worker. The extractor
        # remains covered by tests and can be enabled in a dedicated worker
        # process, but production request handlers should only reconcile stored
        # candidates and mark missing review items as stale.
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for term in _query_terms_for_product(product):
        url = f"https://re-store.ru/search/?q={quote_plus(term)}"
        try:
            html = await _fetch_search_html(url)
        except Exception:
            continue
        for candidate in _extract_restore_search_candidates(html, product):
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url or candidate_url in seen:
                continue
            seen.add(candidate_url)
            out.append(candidate)
            if len(out) >= 5:
                return out
    return out


async def _discover_store77_candidates(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if os.getenv("ENABLE_BROWSER_COMPETITOR_DISCOVERY", "").strip().lower() not in {"1", "true", "yes"}:
        # Browser-backed crawling must run in a dedicated worker, not inside the
        # web API process. Keeping it disabled by default prevents Chromium from
        # killing uvicorn workers and returning random 502 responses.
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in _store77_seed_candidates_for_product(product):
        candidate_url = str(candidate.get("url") or "")
        if candidate_url and candidate_url not in seen:
            seen.add(candidate_url)
            out.append(candidate)
    if out:
        return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
    for term in _query_terms_for_product(product):
        url = f"https://store77.net/search/?q={quote_plus(term)}"
        try:
            html = await fetch_browser_html(url, timeout_ms=20000)
        except Exception:
            continue
        for candidate in _extract_store77_search_candidates(html, product):
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url or candidate_url in seen:
                continue
            seen.add(candidate_url)
            out.append(candidate)
            if len(out) >= 5:
                return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
    for url in _store77_category_urls_for_product(product):
        try:
            html = await fetch_browser_html(url, timeout_ms=20000)
        except Exception:
            continue
        for candidate in _extract_store77_search_candidates(html, product):
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url or candidate_url in seen:
                continue
            seen.add(candidate_url)
            out.append(candidate)
            if len(out) >= 5:
                return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
    return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)


def _store77_category_urls_for_product(product: Dict[str, Any]) -> List[str]:
    title = _norm_match_text(product.get("title"))
    urls: List[str] = []
    match = re.search(r"\biphone\s+(\d{1,2})(?:\s+(pro\s+max|pro|plus|mini))?", title)
    if match:
        generation = match.group(1)
        suffix = re.sub(r"\s+", "_", (match.group(2) or "").strip())
        slug = "_".join(part for part in ("apple", "iphone", generation, suffix) if part)
        variants = [f"https://store77.net/{slug}_2/", f"https://store77.net/{slug}/"]
        for url in variants:
            if url not in urls:
                urls.append(url)
    return urls


def _store77_seed_candidates_for_product(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_title = str(product.get("title") or "").strip()
    normalized_title = _norm_match_text(raw_title)
    category_urls = _store77_category_urls_for_product(product)
    if not category_urls:
        return []
    model_match = re.search(r"\biphone\s+(\d{1,2})(?:\s+(pro\s+max|pro|plus|mini))?", normalized_title)
    memory_match = re.search(r"\b(\d+)\s*(gb|гб|tb|тб)\b", normalized_title)
    if not model_match or not memory_match:
        return []

    generation = model_match.group(1)
    model_suffix = re.sub(r"\s+", "_", (model_match.group(2) or "").strip())
    model_slug = "_".join(part for part in ("iphone", generation, model_suffix) if part)
    memory_slug = f"{memory_match.group(1)}{'tb' if memory_match.group(2) in {'tb', 'тб'} else 'gb'}"

    sim_slug = ""
    sim_label = ""
    sim_profile = _sim_profile(raw_title)
    if sim_profile == "dual_sim":
        sim_slug = "dual_sim"
        sim_label = " Dual Sim"
    elif sim_profile == "nano_sim_esim":
        sim_slug = "nano_sim_esim"
        sim_label = " nano SIM+eSIM"
    elif sim_profile == "esim_only":
        sim_slug = "esim"
        sim_label = " eSim"

    color_options = [
        ("natural_titanium", "Natural Titanium", ("natural titanium", "натуральный титан")),
        ("desert_titanium", "Desert Titanium", ("desert titanium", "пустынный титан")),
        ("black_titanium", "Black Titanium", ("black titanium", "черный титан", "чёрный титан")),
        ("white_titanium", "White Titanium", ("white titanium", "белый титан")),
    ]
    color_slug = ""
    color_label = ""
    raw_title_lower = raw_title.lower()
    for slug, label, aliases in color_options:
        if any(alias in raw_title_lower or alias in normalized_title for alias in aliases):
            color_slug = slug
            color_label = label
            break
    if not color_slug:
        return []

    slug_parts = ["telefon", "apple", model_slug, memory_slug]
    if sim_slug:
        slug_parts.append(sim_slug)
    slug_parts.append(color_slug)
    product_slug = "_".join(slug_parts)
    url = urljoin(category_urls[0], f"{product_slug}/")
    title = f"Телефон Apple iPhone {generation}"
    if model_suffix:
        title += " " + model_suffix.replace("_", " ").title().replace("Max", "Max")
    title += f" {memory_match.group(1)}Gb{sim_label} ({color_label})"
    confidence_score, reasons = _confidence_for_candidate(product, title, "")
    if confidence_score < 0.78:
        return []
    reasons = [*reasons, "store77 URL собран из модели, памяти, SIM и цвета"]
    return [
        {
            "url": url,
            "title": title,
            "confidence_score": min(0.97, max(confidence_score, 0.93)),
            "confidence_reasons": reasons,
            "discovery_strategy": "store77_slug_seed",
            "match_group_key": _model_memory_color_group_key(raw_title),
            "product_sim_profile": sim_profile,
            "candidate_sim_profile": sim_profile,
        }
    ]


def _extract_store77_search_candidates(html: str, product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    deny = ("search", "cart", "basket", "login", "compare", "favorite", "javascript:")
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or any(part in href.lower() for part in deny):
            continue
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if not text:
            title_attr = str(anchor.get("title") or "").strip()
            text = " ".join(title_attr.split())
        if not text:
            continue
        url = urljoin("https://store77.net", href)
        if detect_site(url) != "store77" or url in seen:
            continue
        if not re.search(r"/(catalog/|product/|tovar/|goods?/|telefony_|apple_iphone_)", url, re.I):
            continue
        confidence_score, reasons = _confidence_for_candidate(product, text, "")
        if confidence_score < 0.78:
            continue
        seen.add(url)
        candidates.append(
            {
                "url": url,
                "title": text,
                "confidence_score": confidence_score,
                "confidence_reasons": reasons,
            }
        )
        if len(candidates) >= 5:
            break
    return candidates


def _get_template_or_404(template_id: str) -> Dict[str, Any]:
    db = load_templates_db()
    templates = db.get("templates") or {}
    t = templates.get(template_id)
    if not isinstance(t, dict):
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return t


def _get_template_attrs(template_id: str) -> list[dict]:
    db = load_templates_db()
    attrs_map = db.get("attributes") or {}
    attrs = attrs_map.get(template_id) or []
    if not isinstance(attrs, list):
        return []
    return [a for a in attrs if isinstance(a, dict)]


def _catalog_nodes() -> List[Dict[str, Any]]:
    try:
        from app.api.routes import catalog as catalog_routes  # lazy import

        resp = catalog_routes.list_nodes()
        nodes = resp.get("nodes", []) if isinstance(resp, dict) else []
        return nodes if isinstance(nodes, list) else []
    except Exception:
        return []


def _templates_by_category() -> Dict[str, List[str]]:
    db = load_templates_db()
    templates = db.get("templates") or {}
    out: Dict[str, List[str]] = {}
    if isinstance(templates, dict):
      for tid, tpl in templates.items():
          if not isinstance(tpl, dict):
              continue
          cid = str(tpl.get("category_id") or "").strip()
          if not cid:
              continue
          out.setdefault(cid, []).append(str(tpl.get("id") or tid))
    legacy_map = db.get("category_to_templates") if isinstance(db.get("category_to_templates"), dict) else {}
    for cid, tids in (legacy_map or {}).items():
        if not isinstance(tids, list):
            continue
        for tid in tids:
            tid_s = str(tid or "").strip()
            if tid_s:
                out.setdefault(str(cid), []).append(tid_s)
    single_map = db.get("category_to_template") if isinstance(db.get("category_to_template"), dict) else {}
    for cid, tid in (single_map or {}).items():
        tid_s = str(tid or "").strip()
        if tid_s:
            out.setdefault(str(cid), []).append(tid_s)
    for cid, tids in out.items():
        uniq: List[str] = []
        seen: set[str] = set()
        for tid in tids:
            if tid in seen:
                continue
            seen.add(tid)
            uniq.append(tid)
        out[cid] = uniq
    return out


def _resolve_template_for_category(category_id: str) -> Tuple[Optional[str], Optional[str]]:
    cid = str(category_id or "").strip()
    if not cid:
        return None, None
    cat_map = _templates_by_category()
    nodes = _catalog_nodes()
    parent_by_id: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        if nid and pid:
            parent_by_id[nid] = pid
    cur = cid
    seen: set[str] = set()
    while cur and cur not in seen:
        seen.add(cur)
        tids = cat_map.get(cur) or []
        if tids:
            return str(tids[0]), cur
        cur = parent_by_id.get(cur, "")
    return None, None


def _master_fields(template_id: str) -> list[dict]:
    attrs = _get_template_attrs(template_id)
    out = []
    for a in attrs:
        code = (a.get("code") or "").strip()
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": a.get("name"),
                "type": a.get("type"),
                "scope": a.get("scope"),
                "required": bool(a.get("required")),
            }
        )
    return out


def _template_attr_meta(template_id: str) -> Dict[str, Dict[str, str]]:
    attrs = _get_template_attrs(template_id)
    out: Dict[str, Dict[str, str]] = {}
    for a in attrs:
        if not isinstance(a, dict):
            continue
        code = str(a.get("code") or "").strip()
        if not code:
            continue
        options = a.get("options") if isinstance(a.get("options"), dict) else {}
        out[code] = {
            "type": str(a.get("type") or "").strip(),
            "dict_id": str(options.get("dict_id") or "").strip(),
        }
    return out


def _normalize_mapped_specs(
    template_id: str,
    mapped_specs: Dict[str, str],
) -> Dict[str, str]:
    attr_meta = _template_attr_meta(template_id)
    out: Dict[str, str] = {}
    for code, raw_value in (mapped_specs or {}).items():
        code_s = str(code or "").strip()
        value = str(raw_value or "").strip()
        if not code_s or not value:
            continue
        meta = attr_meta.get(code_s) or {}
        attr_type = str(meta.get("type") or "").strip().lower()
        dict_id = str(meta.get("dict_id") or "").strip()
        if dict_id and attr_type == "select":
            out[code_s] = canonicalize_dictionary_value(dict_id, value)
        else:
            out[code_s] = value
    return out


def _valid_master_codes(template_id: str) -> set[str]:
    return {f["code"] for f in _master_fields(template_id) if isinstance(f, dict) and f.get("code")}


def _service_code_payload() -> Dict[str, List[str]]:
    db = load_dictionaries_db()
    items = db.get("items") if isinstance(db.get("items"), list) else []
    codes: set[str] = set()
    names: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = item.get("meta") if isinstance(item.get("meta"), dict) else {}
        service = meta.get("service")
        if service is not True and service != "true":
            continue
        for value in (item.get("code"), item.get("attr_id"), item.get("id")):
            norm = str(value or "").strip()
            if norm:
                codes.add(norm)
        title = str(item.get("title") or "").strip()
        if title:
            names.add(title)
    return {"codes": sorted(codes), "names": sorted(names)}


def _template_list_payload() -> List[Dict[str, Any]]:
    db = load_templates_db()
    templates = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    out: List[Dict[str, Any]] = []
    for template_id, template in templates.items():
        if not isinstance(template, dict):
            continue
        out.append(
            {
                "id": str(template.get("id") or template_id),
                "name": str(template.get("name") or "Без названия"),
                "category_id": str(template.get("category_id") or "").strip() or None,
            }
        )
    out.sort(key=lambda item: item["name"].lower())
    return out


def _template_flags_payload() -> Dict[str, bool]:
    db = load_competitor_mapping_db()
    items = db.get("templates", {}) or {}
    flags: Dict[str, bool] = {}
    for template_id, row in items.items():
        if isinstance(row, dict) and _is_configured(row):
            flags[str(template_id)] = True
    return flags


def _build_bootstrap_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "templates": _template_list_payload(),
        "flags": _template_flags_payload(),
        "service_codes": _service_code_payload(),
    }


def _invalidate_marketplace_mapping_caches() -> None:
    try:
        from app.api.routes import marketplace_mapping as marketplace_routes

        marketplace_routes._cache_entry(marketplace_routes._import_categories_cache)["ts"] = 0.0
        marketplace_routes._cache_entry(marketplace_routes._import_categories_cache)["payload"] = None
        marketplace_routes._cache_entry(marketplace_routes._attr_categories_cache)["ts"] = 0.0
        marketplace_routes._cache_entry(marketplace_routes._attr_categories_cache)["payload"] = None
        marketplace_routes._cache_entry(marketplace_routes._attr_bootstrap_cache)["ts"] = 0.0
        marketplace_routes._cache_entry(marketplace_routes._attr_bootstrap_cache)["payload"] = None
        marketplace_routes._details_cache_bucket().clear()
        marketplace_routes._value_details_cache_bucket().clear()
        marketplace_routes._persistent_cache_clear(marketplace_routes._import_categories_cache_path())
        marketplace_routes._persistent_cache_clear(marketplace_routes._attr_categories_cache_path())
        marketplace_routes._persistent_cache_clear(marketplace_routes._attr_bootstrap_cache_path())
        marketplace_routes._persistent_attr_details_cache_clear_all()
    except Exception:
        return


def _normalize_mapping_full(template_id: str, mapping_in: Any) -> Dict[str, str]:
    """
    FULL режим: mapping — это финальный объект { code: "field" }.
    """
    if mapping_in is None or not isinstance(mapping_in, dict):
        raise HTTPException(status_code=400, detail="mapping must be an object")

    allowed_codes = _valid_master_codes(template_id)
    mapping: Dict[str, str] = {}

    for k, v in mapping_in.items():
        kk = str(k).strip()
        vv = str(v).strip()
        if not kk or not vv:
            continue
        # ✅ режем мусор — сохраняем только коды из шаблона
        if allowed_codes and kk not in allowed_codes:
            continue
        mapping[kk] = vv

    return mapping


def _apply_mapping_patch(template_id: str, current: Dict[str, Any], patch_in: Any) -> Dict[str, str]:
    """
    PATCH режим: patch_in — это diff:
      { code: "field" } — установить/обновить
      { code: null }    — удалить
    Никаких “стираний” остальных ключей.
    """
    if patch_in is None or not isinstance(patch_in, dict):
        raise HTTPException(status_code=400, detail="mapping must be an object")

    allowed_codes = _valid_master_codes(template_id)
    next_map: Dict[str, str] = {}
    # стартуем с текущего
    if isinstance(current, dict):
        for k, v in current.items():
            kk = str(k).strip()
            vv = str(v).strip() if v is not None else ""
            if kk and vv:
                next_map[kk] = vv

    for k, v in patch_in.items():
        kk = str(k).strip()
        if not kk:
            continue
        if allowed_codes and kk not in allowed_codes:
            # неизвестные коды игнорируем, чтобы не мусорить
            continue

        if v is None:
            # удалить ключ
            if kk in next_map:
                del next_map[kk]
            continue

        vv = str(v).strip()
        if not vv:
            # пустая строка = трактуем как удаление (на всякий)
            if kk in next_map:
                del next_map[kk]
            continue

        next_map[kk] = vv

    return next_map


def _normalize_mapping_by_site(template_id: str, mapping_in: Any) -> Dict[str, Dict[str, str]]:
    if mapping_in is None or not isinstance(mapping_in, dict):
        raise HTTPException(status_code=400, detail="mapping_by_site must be an object")
    out: Dict[str, Dict[str, str]] = {"restore": {}, "store77": {}}
    for site in ("restore", "store77"):
        cur = mapping_in.get(site)
        if isinstance(cur, dict):
            out[site] = _normalize_mapping_full(template_id, cur)
    return out


def _apply_mapping_patch_by_site(template_id: str, current: Any, patch_in: Any) -> Dict[str, Dict[str, str]]:
    if patch_in is None or not isinstance(patch_in, dict):
        raise HTTPException(status_code=400, detail="mapping_by_site must be an object")

    cur_restore = {}
    cur_store = {}
    if isinstance(current, dict):
        cur_restore = current.get("restore") if isinstance(current.get("restore"), dict) else {}
        cur_store = current.get("store77") if isinstance(current.get("store77"), dict) else {}

    next_map = {
        "restore": _apply_mapping_patch(template_id, cur_restore, patch_in.get("restore") or {}),
        "store77": _apply_mapping_patch(template_id, cur_store, patch_in.get("store77") or {}),
    }
    return next_map


def _is_configured(row: Dict[str, Any]) -> bool:
    """
    ✅ Строгий критерий "Настроен":
    - есть обе ссылки
    - и есть хотя бы 1 сопоставление для каждого сайта
    """
    links = row.get("links") or {}
    has_restore = bool((links.get("restore") or "").strip())
    has_store = bool((links.get("store77") or "").strip())
    maps = row.get("mapping_by_site") or {}
    m_restore = maps.get("restore") if isinstance(maps, dict) else {}
    m_store = maps.get("store77") if isinstance(maps, dict) else {}
    has_map_restore = isinstance(m_restore, dict) and len(m_restore) > 0
    has_map_store = isinstance(m_store, dict) and len(m_store) > 0
    return bool(has_restore and has_store and has_map_restore and has_map_store)


def _dedupe_fields(fields: Any) -> list[str]:
    if not isinstance(fields, list):
        return []
    clean: list[str] = []
    seen: set[str] = set()
    for f in fields:
        s = str(f).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        clean.append(s)
    return clean


def _ensure_row_shape(row: Any) -> Dict[str, Any]:
    if not isinstance(row, dict):
        row = {}
    return {
        "priority_site": row.get("priority_site"),
        "links": _validate_links_keep_keys(row.get("links") or {}),
        "mapping_by_site": row.get("mapping_by_site")
        if isinstance(row.get("mapping_by_site"), dict)
        else {
            "restore": dict(row.get("mapping") or {}) if isinstance(row.get("mapping"), dict) else {},
            "store77": dict(row.get("mapping") or {}) if isinstance(row.get("mapping"), dict) else {},
        },
        "updated_at": row.get("updated_at"),
    }


def _get_category_row_with_fallback(category_id: str) -> Tuple[Dict[str, Any], Optional[str], Optional[str]]:
    db = load_competitor_mapping_db()
    category_rows = db.get("categories") if isinstance(db.get("categories"), dict) else {}
    row = _ensure_row_shape((category_rows or {}).get(category_id) or {})
    template_id, source_category_id = _resolve_template_for_category(category_id)
    if any((row.get("links") or {}).values()) or any((row.get("mapping_by_site") or {}).get(site) for site in ("restore", "store77")):
        return row, template_id, source_category_id
    if template_id:
        template_rows = db.get("templates") if isinstance(db.get("templates"), dict) else {}
        legacy_row = _ensure_row_shape((template_rows or {}).get(template_id) or {})
        return legacy_row, template_id, source_category_id
    return row, template_id, source_category_id


# =========================
# API
# =========================
@router.get("/template/{template_id}")
def get_template_mapping(template_id: str) -> Dict[str, Any]:
    tpl = _get_template_or_404(template_id)

    db = load_competitor_mapping_db()
    row = (db.get("templates", {}) or {}).get(template_id) or {}
    row = _ensure_row_shape(row)

    return {
        "ok": True,
        "template_id": template_id,
        "template": {
            "id": tpl.get("id"),
            "name": tpl.get("name"),
            "category_id": tpl.get("category_id"),
        },
        "master_fields": _master_fields(template_id),
        "data": row,
    }


@router.get("/category/{category_id}")
def get_category_mapping(category_id: str) -> Dict[str, Any]:
    category_id = str(category_id or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id required")

    row, template_id, source_category_id = _get_category_row_with_fallback(category_id)
    tpl = _get_template_or_404(template_id) if template_id else None

    return {
        "ok": True,
        "category_id": category_id,
        "template_id": template_id,
        "template_source_category_id": source_category_id,
        "template": {
            "id": tpl.get("id"),
            "name": tpl.get("name"),
            "category_id": tpl.get("category_id"),
        } if isinstance(tpl, dict) else None,
        "master_fields": _master_fields(template_id) if template_id else [],
        "data": row,
    }


@router.put("/template/{template_id}")
def save_template_mapping(template_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ MERGE update (PATCH-like semantics через PUT, чтобы фронт мог слать diff)
    payload может содержать частично:
    {
      "priority_site": "restore"|"store77"|null,         (optional)
      "links": { "restore": "...", "store77": "..." },    (optional; если пришло — перезапишем оба ключа нормализованно)
      "mapping": { "<code>": "<field>" | null }           (optional; diff, null=удалить)
    }
    """
    _ = _get_template_or_404(template_id)  # ✅ проверяем что шаблон существует

    db = load_competitor_mapping_db()
    tpl_rows = db.setdefault("templates", {})
    current_raw = tpl_rows.get(template_id) or {}
    current = _ensure_row_shape(current_raw)

    # priority_site (optional)
    if "priority_site" in payload:
        priority_site = payload.get("priority_site")
        if priority_site is not None and priority_site not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail="Invalid priority_site")
        current["priority_site"] = priority_site

    # links (optional)
    if "links" in payload:
        current["links"] = _validate_links_keep_keys(payload.get("links") or {})

    # mapping_by_site (optional) — diff apply
    if "mapping_by_site" in payload:
        patch = payload.get("mapping_by_site") or {}
        current["mapping_by_site"] = _apply_mapping_patch_by_site(
            template_id,
            current.get("mapping_by_site") or {},
            patch,
        )

    # legacy: mapping (single)
    if "mapping" in payload and "mapping_by_site" not in payload:
        patch = payload.get("mapping") or {}
        merged = _apply_mapping_patch(template_id, (current.get("mapping_by_site") or {}).get("restore") or {}, patch)
        current["mapping_by_site"] = {"restore": merged, "store77": dict(merged)}

    current["updated_at"] = now_iso()

    tpl_rows[template_id] = current
    save_competitor_mapping_db(db)
    cache_entry = _bootstrap_cache_entry()
    cache_entry["payload"] = None
    cache_entry["at"] = 0.0
    _invalidate_marketplace_mapping_caches()

    return {"ok": True, "data": current, "configured": _is_configured(current)}


@router.put("/category/{category_id}")
def save_category_mapping(category_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    category_id = str(category_id or "").strip()
    if not category_id:
        raise HTTPException(status_code=400, detail="category_id required")

    template_id, source_category_id = _resolve_template_for_category(category_id)
    current, _, _ = _get_category_row_with_fallback(category_id)
    if "priority_site" in payload:
        priority_site = payload.get("priority_site")
        if priority_site is not None and priority_site not in ALLOWED_SITES:
            raise HTTPException(status_code=400, detail="Invalid priority_site")
        current["priority_site"] = priority_site
    if "links" in payload:
        current["links"] = _validate_links_keep_keys(payload.get("links") or {})
    if "mapping_by_site" in payload:
        if not template_id:
            raise HTTPException(status_code=400, detail="No effective template for category")
        patch = payload.get("mapping_by_site") or {}
        current["mapping_by_site"] = _apply_mapping_patch_by_site(
            template_id,
            current.get("mapping_by_site") or {},
            patch,
        )
    if "mapping" in payload and "mapping_by_site" not in payload:
        if not template_id:
            raise HTTPException(status_code=400, detail="No effective template for category")
        patch = payload.get("mapping") or {}
        merged = _apply_mapping_patch(template_id, (current.get("mapping_by_site") or {}).get("restore") or {}, patch)
        current["mapping_by_site"] = {"restore": merged, "store77": dict(merged)}
    current["updated_at"] = now_iso()

    db = load_competitor_mapping_db()
    db.setdefault("categories", {})
    db["categories"][category_id] = current
    save_competitor_mapping_db(db)
    cache_entry = _bootstrap_cache_entry()
    cache_entry["payload"] = None
    cache_entry["at"] = 0.0
    _invalidate_marketplace_mapping_caches()

    return {
        "ok": True,
        "category_id": category_id,
        "template_id": template_id,
        "template_source_category_id": source_category_id,
        "data": current,
        "configured": _is_configured(current),
    }


@router.get("/template-flags")
def template_flags() -> Dict[str, Any]:
    """
    Для списка шаблонов: где действительно настроено — ставим галочку.
    Возвращаем map: { template_id: true }
    """
    db = load_competitor_mapping_db()
    items = db.get("templates", {}) or {}

    flags: Dict[str, bool] = {}
    for tid, row in items.items():
        if not isinstance(row, dict):
            continue
        # ✅ важно: используем strict критерий (ссылки + маппинг)
        if _is_configured(row):
            flags[str(tid)] = True

    return {"ok": True, "flags": flags}


@router.get("/bootstrap")
def competitor_mapping_bootstrap() -> Dict[str, Any]:
    now = monotonic()
    cache_entry = _bootstrap_cache_entry()
    cached = cache_entry.get("payload")
    cached_at = float(cache_entry.get("at") or 0.0)
    if cached and (now - cached_at) < _BOOTSTRAP_CACHE_TTL_SECONDS:
        return cached
    payload = _build_bootstrap_payload()
    cache_entry["payload"] = payload
    cache_entry["at"] = now
    return payload


@router.get("/discovery/sources")
def discovery_sources() -> Dict[str, Any]:
    return {"ok": True, "sources": [dict(item) for item in DISCOVERY_SOURCES]}


@router.get("/discovery/candidates")
def discovery_candidates(
    status: Optional[str] = None,
    source_id: Optional[str] = None,
    product_id: Optional[str] = None,
) -> Dict[str, Any]:
    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    items = list((discovery.get("candidates") or {}).values())
    out: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if status and str(item.get("status") or "") != status:
            continue
        if source_id and str(item.get("source_id") or "") != source_id:
            continue
        if product_id and str(item.get("product_id") or "") != product_id:
            continue
        out.append(dict(item))
    out.sort(key=lambda row: (str(row.get("status") or ""), -float(row.get("confidence_score") or 0), str(row.get("last_seen_at") or "")))
    return {
        "ok": True,
        "items": out,
        "count": len(out),
        "sources": [dict(item) for item in DISCOVERY_SOURCES],
    }


@router.get("/discovery/products/{product_id}")
def discovery_product_context(product_id: str) -> Dict[str, Any]:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise HTTPException(status_code=400, detail="product_id is required")

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates_map = discovery.get("candidates") or {}
    links_map = discovery.get("links") or {}

    items: List[Dict[str, Any]] = []
    for item in candidates_map.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("product_id") or "").strip() != normalized_product_id:
            continue
        items.append(dict(item))
    items.sort(key=lambda row: (str(row.get("status") or ""), -float(row.get("confidence_score") or 0), str(row.get("last_seen_at") or "")))

    confirmed_links: List[Dict[str, Any]] = []
    for key, link in links_map.items():
        if not isinstance(link, dict):
            continue
        if str(link.get("product_id") or "").strip() != normalized_product_id and not str(key).startswith(f"{normalized_product_id}:"):
            continue
        confirmed_links.append(dict(link))
    confirmed_links.sort(key=lambda row: (str(row.get("source_id") or ""), str(row.get("confirmed_at") or "")))

    return {
        "ok": True,
        "product_id": normalized_product_id,
        "items": items,
        "confirmed_links": confirmed_links,
        "counts": {
            "total": len(items),
            "needs_review": sum(1 for item in items if item.get("status") == "needs_review"),
            "approved": sum(1 for item in items if item.get("status") == "approved"),
            "rejected": sum(1 for item in items if item.get("status") == "rejected"),
            "stale": sum(1 for item in items if item.get("status") == "stale"),
            "confirmed_links": len(confirmed_links),
        },
        "sources": [dict(item) for item in DISCOVERY_SOURCES],
    }


def _parse_discovery_run_request(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[List[str]], int]:
    requested_sources = payload.get("sources") or [item["id"] for item in DISCOVERY_SOURCES]
    if not isinstance(requested_sources, list):
        raise HTTPException(status_code=400, detail="sources must be a list")
    sources = [_source_by_id(str(item or "").strip()) for item in requested_sources if str(item or "").strip()]
    if not sources:
        raise HTTPException(status_code=400, detail="No competitor sources selected")

    product_ids = payload.get("product_ids")
    if product_ids is not None and not isinstance(product_ids, list):
        raise HTTPException(status_code=400, detail="product_ids must be a list")
    try:
        limit = int(payload.get("limit", 50))
    except Exception:
        limit = 50
    return sources, product_ids, limit


async def _execute_discovery_run(
    run_id: str,
    sources: List[Dict[str, Any]],
    product_ids: Optional[List[str]],
    limit: int,
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    tenant_token = set_current_tenant_organization_id(organization_id) if organization_id else None
    try:
        return await _execute_discovery_run_for_current_tenant(run_id, sources, product_ids, limit)
    finally:
        if tenant_token is not None:
            reset_current_tenant_organization_id(tenant_token)


async def _execute_discovery_run_for_current_tenant(run_id: str, sources: List[Dict[str, Any]], product_ids: Optional[List[str]], limit: int) -> Dict[str, Any]:
    products = _discovery_products(product_ids=product_ids, limit=limit)

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates = discovery["candidates"]
    started_at = now_iso()
    created_count = 0
    updated_count = 0
    errors: List[Dict[str, Any]] = []
    discovery["runs"][run_id] = _remember_discovery_run(_run_payload(
        run_id,
        status="running",
        sources=sources,
        product_ids=product_ids,
        limit=limit,
        started_at=started_at,
    ))
    save_competitor_mapping_db(db)

    for product in products:
        for source in sources:
            product_id = str(product.get("id") or "").strip()
            source_id = str(source.get("id") or "").strip()
            seen_candidate_ids: set[str] = set()
            try:
                raw_candidates = await asyncio.wait_for(
                    _discover_product_candidates_for_source(product, source),
                    timeout=_DISCOVERY_SOURCE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                errors.append(
                    {
                        "product_id": product.get("id"),
                        "source_id": source.get("id"),
                        "error": "DISCOVERY_SOURCE_TIMEOUT",
                    }
                )
                continue
            except Exception as exc:
                errors.append(
                    {
                        "product_id": product.get("id"),
                        "source_id": source.get("id"),
                        "error": str(exc) or "DISCOVERY_FAILED",
                    }
                )
                continue
            if not isinstance(raw_candidates, list):
                continue
            for raw in raw_candidates:
                candidate = _normalize_candidate(product, source, raw)
                if not candidate:
                    continue
                seen_candidate_ids.add(candidate["id"])
                existed = candidates.get(candidate["id"])
                if isinstance(existed, dict):
                    candidate["first_seen_at"] = existed.get("first_seen_at") or candidate["first_seen_at"]
                    if existed.get("status") in {"approved", "rejected"}:
                        candidate["status"] = existed.get("status")
                    candidates[candidate["id"]] = {**existed, **candidate, "last_seen_at": now_iso()}
                    updated_count += 1
                else:
                    candidates[candidate["id"]] = candidate
                    created_count += 1
            for existing_id, existing in list(candidates.items()):
                if not isinstance(existing, dict):
                    continue
                if existing_id in seen_candidate_ids:
                    continue
                if str(existing.get("product_id") or "").strip() != product_id:
                    continue
                if str(existing.get("source_id") or "").strip() != source_id:
                    continue
                if existing.get("status") != "needs_review":
                    continue
                existing["status"] = "stale"
                existing["last_seen_at"] = now_iso()
                existing["confidence_reasons"] = list(existing.get("confidence_reasons") or []) + ["не найдено при повторном discovery"]
                candidates[existing_id] = existing
                updated_count += 1

    run = _run_payload(
        run_id,
        status="completed" if not errors else "completed_with_errors",
        sources=sources,
        product_ids=[str(item.get("id") or "") for item in products],
        limit=limit,
        started_at=started_at,
        finished_at=now_iso(),
        created_count=created_count,
        updated_count=updated_count,
        errors=errors,
        scanned_products_count=len(products),
    )
    discovery["runs"][run_id] = _remember_discovery_run(run)
    save_competitor_mapping_db(db)
    return run


async def _execute_discovery_run_safe(
    run_id: str,
    sources: List[Dict[str, Any]],
    product_ids: Optional[List[str]],
    limit: int,
    organization_id: Optional[str] = None,
) -> None:
    tenant_token = set_current_tenant_organization_id(organization_id) if organization_id else None
    try:
        await _execute_discovery_run_for_current_tenant(run_id, sources, product_ids, limit)
    except Exception as exc:
        db = load_competitor_mapping_db()
        discovery = _ensure_discovery_doc(db)
        discovery["runs"][run_id] = _remember_discovery_run(_run_payload(
            run_id,
            status="failed",
            sources=sources,
            product_ids=product_ids,
            limit=limit,
            finished_at=now_iso(),
            errors=[{"error": str(exc) or "DISCOVERY_FAILED"}],
        ))
        save_competitor_mapping_db(db)
    finally:
        if tenant_token is not None:
            reset_current_tenant_organization_id(tenant_token)


@router.post("/discovery/run")
async def discovery_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    sources, product_ids, limit = _parse_discovery_run_request(payload)
    run_id = _run_id()
    organization_id = current_tenant_organization_id()

    if bool(payload.get("background", False)):
        db = load_competitor_mapping_db()
        discovery = _ensure_discovery_doc(db)
        run = _run_payload(
            run_id,
            status="queued",
            sources=sources,
            product_ids=product_ids,
            limit=limit,
        )
        discovery["runs"][run_id] = _remember_discovery_run(run)
        save_competitor_mapping_db(db)
        _start_discovery_worker_process(run_id, organization_id)
        return {"ok": True, "run": run, "created_count": 0, "updated_count": 0, "errors_count": 0}

    run = await _execute_discovery_run(run_id, sources, product_ids, limit, organization_id)

    return {
        "ok": True,
        "run": run,
        "created_count": int(run.get("created_count") or 0),
        "updated_count": int(run.get("updated_count") or 0),
        "errors_count": int(run.get("errors_count") or 0),
    }


@router.get("/discovery/runs/{run_id}")
def discovery_run_status(run_id: str) -> Dict[str, Any]:
    normalized_run_id = str(run_id or "").strip()
    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    run = (discovery.get("runs") or {}).get(normalized_run_id)
    if not isinstance(run, dict):
        cached = _discovery_run_cache.get(normalized_run_id)
        if isinstance(cached, dict):
            return {"ok": True, "run": cached}
        if normalized_run_id.startswith("run_"):
            # In production a background request and its polling request can hit
            # different worker processes before the persisted run is visible.
            # Keep the UI in polling mode instead of surfacing a false 404.
            return {
                "ok": True,
                "run": _run_payload(
                    normalized_run_id,
                    status="running",
                    sources=[],
                    product_ids=None,
                    limit=1,
                    errors=[{"warning": "RUN_STATUS_PENDING"}],
                ),
            }
        raise HTTPException(status_code=404, detail="Run not found")
    return {"ok": True, "run": run}


@router.post("/discovery/candidates/{candidate_id}/moderate")
def moderate_candidate(candidate_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="action must be approve or reject")

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates = discovery["candidates"]
    candidate = candidates.get(candidate_id)
    if not isinstance(candidate, dict):
        raise HTTPException(status_code=404, detail="Candidate not found")

    reviewed_at = now_iso()
    if action == "approve":
        candidate["status"] = "approved"
        candidate["reviewed_at"] = reviewed_at
        link_key = f"{candidate.get('product_id')}:{candidate.get('source_id')}"
        discovery["links"][link_key] = {
            "id": link_key,
            "product_id": candidate.get("product_id"),
            "source_id": candidate.get("source_id"),
            "candidate_id": candidate_id,
            "url": candidate.get("url"),
            "status": "confirmed",
            "confirmed_at": reviewed_at,
            "last_checked_at": candidate.get("last_seen_at") or reviewed_at,
        }
        match_group_key = str(candidate.get("match_group_key") or "").strip()
        product_id = str(candidate.get("product_id") or "").strip()
        source_id = str(candidate.get("source_id") or "").strip()
        if match_group_key and product_id and source_id:
            for sibling_id, sibling in candidates.items():
                if sibling_id == candidate_id or not isinstance(sibling, dict):
                    continue
                if sibling.get("status") != "needs_review":
                    continue
                if str(sibling.get("product_id") or "").strip() != product_id:
                    continue
                if str(sibling.get("source_id") or "").strip() != source_id:
                    continue
                if str(sibling.get("match_group_key") or "").strip() != match_group_key:
                    continue
                sibling["status"] = "rejected"
                sibling["reviewed_at"] = reviewed_at
                sibling["rejection_reason"] = "sibling_not_selected"
                sibling["confidence_reasons"] = list(sibling.get("confidence_reasons") or []) + ["отклонено автоматически: выбран другой вариант группы"]
                candidates[sibling_id] = sibling
    else:
        candidate["status"] = "rejected"
        candidate["reviewed_at"] = reviewed_at
        candidate["rejection_reason"] = str(payload.get("reason") or "").strip()

    candidates[candidate_id] = candidate
    save_competitor_mapping_db(db)
    return {"ok": True, "candidate": candidate, "links": discovery.get("links") or {}}


@router.post("/discovery/products/{product_id}/links")
def add_manual_competitor_link(product_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise HTTPException(status_code=400, detail="product_id required")
    source_id = str(payload.get("source_id") or "").strip()
    url = str(payload.get("url") or "").strip()
    if source_id not in ALLOWED_SITES:
        raise HTTPException(status_code=400, detail="Unknown competitor source")
    if not url:
        raise HTTPException(status_code=400, detail="url required")
    if detect_site(url) != source_id:
        raise HTTPException(status_code=400, detail="Парсинг запрещён: ссылка не из разрешённого источника")

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    reviewed_at = now_iso()
    link_key = f"{normalized_product_id}:{source_id}"
    discovery["links"][link_key] = {
        "id": link_key,
        "product_id": normalized_product_id,
        "source_id": source_id,
        "candidate_id": f"manual:{link_key}",
        "url": url,
        "status": "confirmed",
        "confirmed_at": reviewed_at,
        "last_checked_at": reviewed_at,
        "source": "manual",
    }
    for candidate_id, candidate in list((discovery.get("candidates") or {}).items()):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("product_id") or "").strip() != normalized_product_id:
            continue
        if str(candidate.get("source_id") or "").strip() != source_id:
            continue
        if candidate.get("status") != "needs_review":
            continue
        candidate["status"] = "rejected"
        candidate["reviewed_at"] = reviewed_at
        candidate["rejection_reason"] = "manual_link_selected"
        candidate["confidence_reasons"] = list(candidate.get("confidence_reasons") or []) + ["отклонено автоматически: пользователь добавил ссылку вручную"]
        discovery["candidates"][candidate_id] = candidate
    save_competitor_mapping_db(db)
    return {"ok": True, "link": discovery["links"][link_key], "links": discovery.get("links") or {}}


@router.post("/discovery/products/{product_id}/enrich")
async def enrich_product_from_confirmed_competitors(product_id: str) -> Dict[str, Any]:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise HTTPException(status_code=400, detail="product_id required")

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    confirmed_links = _confirmed_links_for_product(discovery, normalized_product_id)
    if not confirmed_links:
        raise HTTPException(status_code=400, detail="Для товара нет подтвержденных ссылок конкурентов")

    products = query_products_full(ids=[normalized_product_id])
    product = products[0] if products else None
    if not isinstance(product, dict):
        raise HTTPException(status_code=404, detail="Product not found")

    link_by_source = {str(link.get("source_id") or "").strip(): link for link in confirmed_links}

    async def _one(link: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        source_id = str(link.get("source_id") or "").strip()
        url = str(link.get("url") or "").strip()
        try:
            result = await extract_competitor_content(url)
            specs = result.get("specs") if isinstance(result.get("specs"), dict) else {}
            return source_id, {
                "ok": True,
                "site": source_id,
                "url": url,
                "images": result.get("images") if isinstance(result.get("images"), list) else [],
                "specs": specs,
                "description": str(result.get("description") or "").strip(),
            }
        except Exception as exc:
            return source_id, {
                "ok": False,
                "site": source_id,
                "url": url,
                "error": str(exc) or "EXTRACT_FAILED",
            }

    extracted_pairs = await asyncio.gather(*[_one(link) for link in confirmed_links])
    extracted = {source_id: result for source_id, result in extracted_pairs if source_id}
    successful = {source_id: result for source_id, result in extracted.items() if result.get("ok")}
    errors = [
        {"source_id": source_id, "url": result.get("url"), "error": result.get("error") or "EXTRACT_FAILED"}
        for source_id, result in extracted.items()
        if not result.get("ok")
    ]
    if not successful:
        return {
            "ok": False,
            "product_id": normalized_product_id,
            "enriched_sources": [],
            "matched_count": 0,
            "unmatched_count": 0,
            "errors": errors,
        }

    merged = _merge_competitor_content_into_product(product, extracted=successful, links=link_by_source)
    saved = upsert_product_item(merged["product"])
    for source_id in successful.keys():
        link_key = f"{normalized_product_id}:{source_id}"
        link = discovery.get("links", {}).get(link_key)
        if isinstance(link, dict):
            link["last_checked_at"] = now_iso()
            link["last_enriched_at"] = now_iso()
            discovery["links"][link_key] = link
    save_competitor_mapping_db(db)
    return {
        "ok": True,
        "product_id": normalized_product_id,
        "product": saved or merged["product"],
        "enriched_sources": merged["enriched_sources"],
        "matched_count": merged["matched_count"],
        "unmatched_count": merged["unmatched_count"],
        "errors": errors,
    }


@router.post("/competitor-fields")
async def competitor_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ Реально вытаскиваем поля конкурента (restore/store77).
    UI сможет делать mapping через dropdown.
    """
    url = (payload.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="url required")

    site = detect_site(url)
    if not site:
        raise HTTPException(status_code=400, detail="Парсинг запрещён: сайт не разрешён")

    try:
        result = await extract_competitor_fields(url, return_meta=True)
    except Exception as e:
        msg = str(e) or "EXTRACT_FAILED"
        raise HTTPException(status_code=500, detail=msg)

    fields = (result or {}).get("fields") if isinstance(result, dict) else result
    fields_meta = (result or {}).get("fields_meta") if isinstance(result, dict) else []
    return {
        "ok": True,
        "site": site,
        "fields": _dedupe_fields(fields),
        "fields_meta": fields_meta,
    }


@router.post("/competitor-fields-batch")
async def competitor_fields_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    ✅ Батч-режим: одним запросом грузим поля для обеих ссылок.
    payload:
    {
      "links": { "restore": "...", "store77": "..." }
    }
    """
    links = payload.get("links") or {}
    norm_links = _validate_links_keep_keys(links)

    async def _one(site_key: str, url: str) -> Dict[str, Any]:
        url = (url or "").strip()
        if not url:
            return {"ok": True, "site": site_key, "fields": [], "skipped": True}

        site = detect_site(url)
        if site != site_key:
            return {"ok": False, "error": "Парсинг запрещён: сайт не разрешён"}

        try:
            result = await extract_competitor_fields(url, return_meta=True)
        except Exception as e:
            msg = str(e) or "EXTRACT_FAILED"
            return {"ok": False, "error": msg}

        fields = (result or {}).get("fields") if isinstance(result, dict) else result
        fields_meta = (result or {}).get("fields_meta") if isinstance(result, dict) else []
        return {
            "ok": True,
            "site": site_key,
            "fields": _dedupe_fields(fields),
            "fields_meta": fields_meta,
            "skipped": False,
        }

    import asyncio

    res = await asyncio.gather(
        _one("restore", norm_links.get("restore", "")),
        _one("store77", norm_links.get("store77", "")),
        return_exceptions=True,
    )

    def _unwrap(item: Any) -> Dict[str, Any]:
        if isinstance(item, Exception):
            return {"ok": False, "error": "EXTRACT_FAILED"}
        if isinstance(item, dict):
            return item
        return {"ok": False, "error": "EXTRACT_FAILED"}

    r_restore = _unwrap(res[0] if len(res) > 0 else Exception("missing"))
    r_store77 = _unwrap(res[1] if len(res) > 1 else Exception("missing"))

    return {"ok": True, "results": {"restore": r_restore, "store77": r_store77}}


@router.post("/competitor-content-batch")
async def competitor_content_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Загружает контент (specs + media + description) для двух ссылок.
    payload:
    {
      "links": { "restore": "...", "store77": "..." }
    }
    """
    template_id = payload.get("template_id")
    mapping_by_site: Dict[str, Dict[str, str]] = {"restore": {}, "store77": {}}
    if isinstance(template_id, str) and template_id:
        db = load_competitor_mapping_db()
        row = (db.get("templates", {}) or {}).get(template_id) or {}
        row = _ensure_row_shape(row)
        mapping_by_site = row.get("mapping_by_site") or {"restore": {}, "store77": {}}

    def _norm_key(v: str) -> str:
        return " ".join(str(v or "").split()).lower()

    def _map_specs(specs: Dict[str, str], mapping: Dict[str, str]) -> Dict[str, str]:
        if not specs or not mapping:
            return {}
        norm_specs = {_norm_key(k): v for k, v in specs.items() if k}
        out: Dict[str, str] = {}
        for code, field in (mapping or {}).items():
            field_key = _norm_key(field)
            if not field_key:
                continue
            out[code] = norm_specs.get(field_key, "")
        return out

    links = payload.get("links") or {}
    norm_links = _validate_links_keep_keys(links)

    async def _one(site_key: str, url: str) -> Dict[str, Any]:
        url = (url or "").strip()
        if not url:
            return {"ok": True, "site": site_key, "images": [], "specs": {}, "description": "", "skipped": True}

        site = detect_site(url)
        if site != site_key:
            return {"ok": False, "error": "Парсинг запрещён: сайт не разрешён"}

        try:
            result = await extract_competitor_content(url)
        except Exception as e:
            msg = str(e) or "EXTRACT_FAILED"
            return {"ok": False, "error": msg}

        specs = result.get("specs") or {}
        mapped_specs_raw = _map_specs(specs, mapping_by_site.get(site_key, {}) or {})
        return {
            "ok": True,
            "site": site_key,
            "images": result.get("images") or [],
            "specs": specs,
            "mapped_specs_raw": mapped_specs_raw,
            "mapped_specs": _normalize_mapped_specs(template_id, mapped_specs_raw) if template_id else mapped_specs_raw,
            "description": result.get("description") or "",
            "skipped": False,
        }

    import asyncio

    res = await asyncio.gather(
        _one("restore", norm_links.get("restore", "")),
        _one("store77", norm_links.get("store77", "")),
        return_exceptions=True,
    )

    def _unwrap(item: Any) -> Dict[str, Any]:
        if isinstance(item, Exception):
            return {"ok": False, "error": "EXTRACT_FAILED"}
        if isinstance(item, dict):
            return item
        return {"ok": False, "error": "EXTRACT_FAILED"}

    r_restore = _unwrap(res[0] if len(res) > 0 else Exception("missing"))
    r_store77 = _unwrap(res[1] if len(res) > 1 else Exception("missing"))

    return {"ok": True, "results": {"restore": r_restore, "store77": r_store77}}
