# backend/app/api/routes/competitor_mapping.py
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import html as html_lib
import json
import mimetypes
import os
from pathlib import Path
import re
import subprocess
import sys
from time import monotonic
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import quote, quote_plus, urljoin, urlparse

import httpx

from fastapi import APIRouter, HTTPException

from app.core.llm import LlmError, llm_chat_text
from app.core.object_storage import ObjectStorageError, s3_enabled, upload_bytes
from app.core.products.parameter_flow import dict_id_for_product_feature
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
from app.storage.relational_pim_store import (
    get_pim_workflow_run,
    list_pim_channel_links,
    query_products_full,
    upsert_pim_channel_link,
    upsert_pim_workflow_run,
    upsert_product_item,
)
from app.core.value_mapping import canonicalize_dictionary_value

# ✅ Реальный извлекатель полей конкурента (Playwright + restore/store77 парсеры)
from app.core.competitors.extract_competitor_fields import (
    extract_competitor_fields,
    extract_competitor_content,
)
from app.core.competitors.restore_specs import extract_restore_product_content_from_html

router = APIRouter(prefix="/competitor-mapping", tags=["competitor-mapping"])

_BOOTSTRAP_CACHE_TTL_SECONDS = 300.0
_DISCOVERY_SOURCE_TIMEOUT_SECONDS = 32.0
_STORE77_CATEGORY_HTML_CACHE_TTL_SECONDS = 180.0
_ACTIONABLE_DISCOVERY_CONFIDENCE_SCORE = 0.78
_VISIBLE_DISCOVERY_CONFIDENCE_SCORE = 0.45
_bootstrap_cache: Dict[str, Dict[str, Any]] = {}
_discovery_run_cache: Dict[str, Dict[str, Any]] = {}
_store77_category_html_cache: Dict[str, Tuple[float, str]] = {}

_AI_SPEC_ACTIONS = {"map_existing", "create_attribute", "ignore"}


# =========================
# helpers
# =========================
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key() -> str:
    return str(current_tenant_organization_id() or "org_default").strip() or "org_default"


def _bootstrap_cache_entry() -> Dict[str, Any]:
    return _bootstrap_cache.setdefault(_cache_key(), {"at": 0.0, "payload": None})


def _safe_storage_segment(value: Any, fallback: str) -> str:
    raw = str(value or "").strip() or fallback
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)
    return safe.strip("_") or fallback


def _media_extension_from_url(url: str, content_type: str = "") -> str:
    parsed = urlparse(str(url or "").strip())
    suffix = Path(parsed.path or "").suffix.lower().lstrip(".")
    if suffix in {"jpg", "jpeg", "png", "webp"}:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip())
    if guessed:
        normalized = guessed.lower().lstrip(".")
        if normalized in {"jpg", "jpeg", "png", "webp"}:
            return normalized
    return "jpg"


def _is_internal_upload_url(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    path_value = parsed.path or str(url or "").strip()
    return path_value.startswith("/api/uploads/")


def _store77_js_challenge_hash(code: int) -> int:
    value = 123456789
    counter = 0
    for index in range(1677696):
        value = ((value + code) ^ (value + (value % 3) + (value % 17) + code) ^ index) % 16776960
        if value % 117 == 0:
            counter = (counter + 1) % 1111
    return counter


def _apply_store77_js_challenge_cookies(client: httpx.AsyncClient, user_agent: str) -> bool:
    raw_cookie = str(client.cookies.get("__js_p_") or "").strip()
    if not raw_cookie:
        return False
    try:
        code = int(raw_cookie.split(",", 1)[0])
    except (TypeError, ValueError):
        return False
    client.cookies.set("__jhash_", str(_store77_js_challenge_hash(code)), domain="store77.net", path="/")
    client.cookies.set("__jua_", quote(user_agent, safe=""), domain="store77.net", path="/")
    return True


async def _import_competitor_image_to_storage(
    *,
    image_url: str,
    product: Dict[str, Any],
    source_id: str,
    source_url: str,
) -> Optional[Dict[str, Any]]:
    if not s3_enabled():
        return None

    url = str(image_url or "").strip()
    if not url:
        return None

    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    headers = {
        "User-Agent": user_agent,
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
    }
    if source_url:
        headers["Referer"] = source_url

    try:
        async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=True, verify=False) as client:
            response = await client.get(url)
            content_type = str(response.headers.get("content-type") or mimetypes.guess_type(url)[0] or "image/jpeg").split(";", 1)[0]
            if "store77.net" in (urlparse(url).hostname or "") and not content_type.startswith("image/"):
                if _apply_store77_js_challenge_cookies(client, user_agent):
                    response = await client.get(url)
                    content_type = str(response.headers.get("content-type") or mimetypes.guess_type(url)[0] or "image/jpeg").split(";", 1)[0]
            response.raise_for_status()
            data = response.content
    except Exception:
        return None

    return _upload_competitor_image_bytes(
        image_url=url,
        data=data,
        content_type=content_type,
        product=product,
        source_id=source_id,
    )


def _upload_competitor_image_bytes(
    *,
    image_url: str,
    data: bytes,
    content_type: str,
    product: Dict[str, Any],
    source_id: str,
) -> Optional[Dict[str, Any]]:
    if not s3_enabled() or not data or len(data) > 12 * 1024 * 1024:
        return None

    normalized_content_type = str(content_type or mimetypes.guess_type(image_url)[0] or "image/jpeg").split(";", 1)[0]
    if not normalized_content_type.startswith("image/"):
        return None

    storage_key = _safe_storage_segment(product.get("sku_pim") or product.get("id"), "product")
    source_key = _safe_storage_segment(source_id, "competitor")
    digest = hashlib.sha1(str(image_url or "").encode("utf-8")).hexdigest()[:20]
    ext = _media_extension_from_url(image_url, normalized_content_type)
    relative_key = f"media_images/{storage_key}/competitors/{source_key}/{digest}.{ext}"

    try:
        meta = upload_bytes(relative_key, data, normalized_content_type)
    except ObjectStorageError:
        return None

    return {
        "url": f"/api/uploads/{relative_key}",
        "external_url": image_url,
        "content_type": meta.content_type,
        "size": meta.size,
        "storage": "s3",
    }


async def _fetch_store77_images_with_browser(image_urls: List[str], source_url: str) -> Dict[str, Tuple[bytes, str]]:
    urls = [str(url or "").strip() for url in image_urls if str(url or "").strip()]
    if not urls:
        return {}

    try:
        from playwright.async_api import async_playwright
    except Exception:
        return {}

    out: Dict[str, Tuple[bytes, str]] = {}
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/123.0.0.0 Safari/537.36"
                ),
                locale="ru-RU",
                timezone_id="Europe/Moscow",
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            page = await context.new_page()
            try:
                await page.goto(source_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(1200)
            except Exception:
                pass

            for url in urls[:24]:
                try:
                    response = await context.request.get(url, headers={"Referer": source_url, "Accept": "image/*,*/*;q=0.8"}, timeout=15000)
                    if response.status >= 400:
                        continue
                    content_type = str(response.headers.get("content-type") or mimetypes.guess_type(url)[0] or "")
                    if not content_type.startswith("image/"):
                        continue
                    body = await response.body()
                    if body:
                        out[url] = (body, content_type)
                except Exception:
                    continue
            await context.close()
            await browser.close()
    except Exception:
        return out
    return out


async def _extract_competitor_content_with_retry(url: str, *, attempts: int = 2) -> Dict[str, Any]:
    last_error: Optional[BaseException] = None
    normalized_attempts = max(1, int(attempts or 1))
    for attempt in range(normalized_attempts):
        try:
            result = await extract_competitor_content(url)
            if isinstance(result, dict):
                result["attempts"] = attempt + 1
            return result
        except Exception as exc:
            last_error = exc
            if attempt + 1 < normalized_attempts:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_error or RuntimeError("EXTRACT_FAILED")


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

_COMPETITOR_MAPPING_SCOPE = "competitor_mapping"
_COMPETITOR_MAPPING_META_PROVIDER = "__meta"
_COMPETITOR_DISCOVERY_WORKFLOW = "competitor_discovery"


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


def _mapping_link_id(entity_type: str, entity_id: str, provider: str) -> str:
    return f"competitor_mapping:{entity_type}:{entity_id}:{provider}"


def _empty_mapping_row() -> Dict[str, Any]:
    return {
        "priority_site": None,
        "links": {k: "" for k in ALLOWED_SITES.keys()},
        "mapping_by_site": {k: {} for k in ALLOWED_SITES.keys()},
        "updated_at": None,
    }


def _mapping_row_has_content(row: Dict[str, Any]) -> bool:
    links = row.get("links") if isinstance(row.get("links"), dict) else {}
    maps = row.get("mapping_by_site") if isinstance(row.get("mapping_by_site"), dict) else {}
    return bool(
        row.get("priority_site")
        or any(str(value or "").strip() for value in links.values())
        or any(isinstance(maps.get(site), dict) and bool(maps.get(site)) for site in ALLOWED_SITES.keys())
    )


def _relational_competitor_mapping_row(entity_type: str, entity_id: str) -> Optional[Dict[str, Any]]:
    normalized_entity_type = str(entity_type or "").strip()
    normalized_entity_id = str(entity_id or "").strip()
    if not normalized_entity_type or not normalized_entity_id:
        return None
    try:
        rows = list_pim_channel_links(
            scope=_COMPETITOR_MAPPING_SCOPE,
            entity_type=normalized_entity_type,
            entity_id=normalized_entity_id,
        )
    except Exception:
        return None
    if not rows:
        return None
    out = _empty_mapping_row()
    for item in rows:
        provider = str(item.get("provider") or "").strip()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        updated_at = item.get("updated_at") or payload.get("updated_at")
        if updated_at:
            out["updated_at"] = updated_at
        if provider == _COMPETITOR_MAPPING_META_PROVIDER:
            priority_site = payload.get("priority_site")
            out["priority_site"] = priority_site if priority_site in ALLOWED_SITES else None
            continue
        if provider not in ALLOWED_SITES:
            continue
        out["links"][provider] = str(item.get("url") or "").strip()
        mapping = payload.get("mapping") if isinstance(payload.get("mapping"), dict) else {}
        out["mapping_by_site"][provider] = {str(k): str(v) for k, v in mapping.items() if str(k).strip() and str(v).strip()}
        priority_site = payload.get("priority_site")
        if priority_site in ALLOWED_SITES:
            out["priority_site"] = priority_site
    return out if _mapping_row_has_content(out) else None


def _persist_competitor_mapping_row(entity_type: str, entity_id: str, row: Dict[str, Any]) -> None:
    normalized_entity_type = str(entity_type or "").strip()
    normalized_entity_id = str(entity_id or "").strip()
    if normalized_entity_type not in {"template", "category"} or not normalized_entity_id:
        return
    shaped = _ensure_row_shape(row)
    priority_site = shaped.get("priority_site") if shaped.get("priority_site") in ALLOWED_SITES else None
    updated_at = shaped.get("updated_at") or now_iso()
    upsert_pim_channel_link(
        {
            "link_id": _mapping_link_id(normalized_entity_type, normalized_entity_id, _COMPETITOR_MAPPING_META_PROVIDER),
            "scope": _COMPETITOR_MAPPING_SCOPE,
            "entity_type": normalized_entity_type,
            "entity_id": normalized_entity_id,
            "provider": _COMPETITOR_MAPPING_META_PROVIDER,
            "status": "configured" if _mapping_row_has_content(shaped) else "empty",
            "source": "competitor_mapping",
            "payload": {
                "priority_site": priority_site,
                "updated_at": updated_at,
            },
        }
    )
    links = shaped.get("links") if isinstance(shaped.get("links"), dict) else {}
    mapping_by_site = shaped.get("mapping_by_site") if isinstance(shaped.get("mapping_by_site"), dict) else {}
    for provider in ALLOWED_SITES.keys():
        mapping = mapping_by_site.get(provider) if isinstance(mapping_by_site.get(provider), dict) else {}
        url = str(links.get(provider) or "").strip()
        status = "configured" if url or mapping else "empty"
        upsert_pim_channel_link(
            {
                "link_id": _mapping_link_id(normalized_entity_type, normalized_entity_id, provider),
                "scope": _COMPETITOR_MAPPING_SCOPE,
                "entity_type": normalized_entity_type,
                "entity_id": normalized_entity_id,
                "provider": provider,
                "url": url,
                "status": status,
                "source": "competitor_mapping",
                "payload": {
                    "priority_site": priority_site,
                    "mapping": mapping,
                    "updated_at": updated_at,
                },
            }
        )


def _remove_legacy_competitor_mapping_row(entity_type: str, entity_id: str) -> None:
    db = load_competitor_mapping_db()
    key = "templates" if entity_type == "template" else "categories"
    rows = db.get(key) if isinstance(db.get(key), dict) else {}
    if str(entity_id) in rows:
        rows.pop(str(entity_id), None)
        db[key] = rows
        save_competitor_mapping_db(db)


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


def _save_competitor_mapping_runs_only(db: Dict[str, Any]) -> None:
    discovery = _ensure_discovery_doc(db)
    candidates = discovery.get("candidates") if isinstance(discovery.get("candidates"), dict) else {}
    links = discovery.get("links") if isinstance(discovery.get("links"), dict) else {}
    candidate_by_id = {
        str(key): value
        for key, value in candidates.items()
        if isinstance(value, dict)
    }
    for candidate in candidate_by_id.values():
        _persist_competitor_channel_candidate(candidate)
    for link in links.values():
        if not isinstance(link, dict):
            continue
        _persist_competitor_channel_link(link, candidate_by_id.get(str(link.get("candidate_id") or "")))
    for run in (discovery.get("runs") or {}).values():
        if isinstance(run, dict):
            _persist_discovery_run(run)
    # Competitor candidates and product links are relational in
    # pim_channel_links. Runs are relational in pim_workflow_runs. JSON remains
    # only as migration fallback for older deployments.
    discovery["candidates"] = {}
    discovery["links"] = {}
    discovery["runs"] = {}
    save_competitor_mapping_db(db)


def _candidate_id(product_id: str, source_id: str, url: str) -> str:
    raw = f"{product_id}|{source_id}|{url}".encode("utf-8")
    return "cand_" + hashlib.sha1(raw).hexdigest()[:16]


def _source_scan_link_id(product_id: str, source_id: str) -> str:
    return f"{product_id}:{source_id}:scan"


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


def _persist_discovery_run(run: Dict[str, Any]) -> Dict[str, Any]:
    remembered = _remember_discovery_run(run)
    try:
        upsert_pim_workflow_run(remembered, workflow=_COMPETITOR_DISCOVERY_WORKFLOW)
    except Exception:
        pass
    return remembered


def _get_discovery_run(run_id: str) -> Optional[Dict[str, Any]]:
    normalized_run_id = str(run_id or "").strip()
    if not normalized_run_id:
        return None
    try:
        run = get_pim_workflow_run(normalized_run_id, workflow=_COMPETITOR_DISCOVERY_WORKFLOW)
        if isinstance(run, dict):
            return run
    except Exception:
        pass
    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    run = (discovery.get("runs") or {}).get(normalized_run_id)
    return dict(run) if isinstance(run, dict) else None


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    return _backend_root().parent


def _start_discovery_worker_process(run_id: str, organization_id: Optional[str]) -> None:
    env = os.environ.copy()
    backend_root = str(_backend_root())
    existing_pythonpath = str(env.get("PYTHONPATH") or "").strip()
    env["PYTHONPATH"] = backend_root if not existing_pythonpath else f"{backend_root}{os.pathsep}{existing_pythonpath}"
    env.setdefault("ENABLE_HTTP_COMPETITOR_DISCOVERY", "1")
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
        "match_group_key": str(raw.get("match_group_key") or _model_memory_color_group_key(raw.get("profile_text") or raw.get("title") or product.get("title"))),
        "product_sim_profile": _sim_profile(product.get("title")),
        "candidate_sim_profile": _sim_profile(raw.get("profile_text") or raw.get("title")),
        "profile_text": str(raw.get("profile_text") or "").strip(),
        "profile_specs": raw.get("profile_specs") if isinstance(raw.get("profile_specs"), dict) else {},
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
    requested_limit = max(1, int(limit or 3))
    if ids:
        return items[: min(requested_limit, 50)]
    return items[: min(requested_limit, 3)]


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
    "airpods",
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
    "airpods",
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
    "magsafe",
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
    tokens = normalized.split()
    has_esim = "esim" in tokens or any(tokens[idx] == "e" and idx + 1 < len(tokens) and tokens[idx + 1] == "sim" for idx in range(len(tokens)))
    has_standalone_sim = any(
        token in {"sim", "сим"}
        and not (idx > 0 and tokens[idx - 1] == "e")
        and not (idx > 0 and tokens[idx - 1] in {"электронная", "электронной", "электронную", "электронные"})
        for idx, token in enumerate(tokens)
    )
    has_nano = "nano sim" in normalized or "nanosim" in normalized or "nano" in tokens
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
    if has_esim and (has_nano or has_standalone_sim):
        return "nano_sim_esim"
    if has_esim:
        return "esim_only"
    if has_nano or has_standalone_sim:
        return "physical_sim"
    return "unknown"


def _model_memory_color_group_key(value: Any) -> str:
    profile = _variant_profile(value)
    return "|".join(str(profile.get(key) or "") for key in ("model", "memory", "color", "sim") if profile.get(key))


def _variant_profile(value: Any) -> Dict[str, str]:
    normalized = _norm_match_text(value)
    raw_lower = str(value or "").lower()
    profile: Dict[str, str] = {}

    model_match = re.search(r"\biphone\s+(\d{1,2})(?:\s+(pro\s+max|pro|plus|mini))?", normalized)
    memory_match = re.search(r"\b(\d+)\s*(gb|гб|tb|тб)\b", normalized)
    if model_match:
        generation = model_match.group(1)
        suffix = re.sub(r"\s+", "_", (model_match.group(2) or "").strip())
        profile["model"] = "_".join(part for part in ("iphone", generation, suffix) if part)
    if memory_match:
        profile["memory"] = f"{memory_match.group(1)}{'tb' if memory_match.group(2) in {'tb', 'тб'} else 'gb'}"

    color_options = [
        ("natural_titanium", ("natural titanium", "натуральный титан", "natural", "натуральн")),
        ("desert_titanium", ("desert titanium", "пустынный титан", "desert", "пустынн")),
        ("black_titanium", ("black titanium", "черный титан", "чёрный титан", "black", "черный", "чёрный")),
        ("white_titanium", ("white titanium", "белый титан", "white", "белый")),
        ("silver", ("silver", "серебрист", "серебро")),
        ("blue", ("blue", "синий", "голубой")),
        ("green", ("green", "зеленый", "зелёный")),
        ("orange", ("orange", "оранжевый", "оранжев")),
        ("pink", ("pink", "розовый")),
        ("yellow", ("yellow", "желтый", "жёлтый")),
    ]
    for slug, aliases in color_options:
        if any(alias in raw_lower or alias in normalized for alias in aliases):
            profile["color"] = slug
            break

    sim = _sim_profile(value)
    if sim != "unknown":
        profile["sim"] = sim

    if re.search(r"\b(global|глобал|международн)\b", normalized):
        profile["region"] = "global"
    elif re.search(r"\b(eac|ростест|ru|русская|россия|рф)\b", normalized):
        profile["region"] = "ru"
    elif re.search(r"\b(china|cn|китай)\b", normalized):
        profile["region"] = "china"
    elif re.search(r"\b(usa|us|сша|америка)\b", normalized):
        profile["region"] = "usa"
    return profile


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
    if "airpods" in tokens:
        required.add("airpods")
        required.update(token for token in tokens if re.fullmatch(r"\d{1,2}", token))
    return required


def _has_token(tokens: set[str], token: str) -> bool:
    return token in tokens


def _apple_line_conflict(product_tokens: set[str], candidate_tokens: set[str]) -> Optional[str]:
    if "airpods" in product_tokens and "airpods" in candidate_tokens:
        for tier in ("pro", "max"):
            if _has_token(product_tokens, tier) != _has_token(candidate_tokens, tier):
                return f"конфликт линейки AirPods: PIM={tier in product_tokens and tier or 'base'}, candidate={tier in candidate_tokens and tier or 'base'}"
        product_has_anc = "anc" in product_tokens
        candidate_has_anc = "anc" in candidate_tokens or "шумоподавлением" in candidate_tokens or "шумоподавление" in candidate_tokens
        if product_has_anc != candidate_has_anc:
            return "конфликт линейки AirPods: ANC"
    return None


def _confidence_for_candidate(product: Dict[str, Any], title: str, sku: str, brand: str = "") -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    product_profile = _variant_profile(product.get("title"))
    candidate_profile = _variant_profile(f"{brand} {title}")
    product_sim = product_profile.get("sim") or "unknown"
    candidate_sim = candidate_profile.get("sim") or "unknown"
    if product_sim != "unknown" and candidate_sim != "unknown" and product_sim != candidate_sim:
        return 0.0, [f"конфликт SIM: PIM={product_sim}, candidate={candidate_sim}"]
    for key, label in (
        ("model", "модели"),
        ("memory", "памяти"),
        ("color", "цвета"),
        ("region", "региона"),
    ):
        product_value = product_profile.get(key)
        candidate_value = candidate_profile.get(key)
        if product_value and candidate_value and product_value != candidate_value:
            return 0.0, [f"конфликт {label}: PIM={product_value}, candidate={candidate_value}"]
    product_sku = str(product.get("sku_gt") or product.get("sku_pim") or "").strip()
    if product_sku and sku and product_sku.lower() == sku.lower():
        score += 0.25
        reasons.append("SKU совпал")
    product_title = _norm_match_text(product.get("title"))
    candidate_title = _norm_match_text(title)
    product_tokens_for_line = _match_tokens(product_title)
    candidate_tokens_for_line = _match_tokens(f"{brand} {title}")
    line_conflict = _apple_line_conflict(product_tokens_for_line, candidate_tokens_for_line)
    if line_conflict:
        return 0.0, [line_conflict]
    product_brand_tokens = _brand_tokens(product.get("title"))
    candidate_brand_tokens = _brand_tokens(brand) | _brand_tokens(title)
    if product_brand_tokens and candidate_brand_tokens and product_brand_tokens.isdisjoint(candidate_brand_tokens):
        return 0.0, ["конфликт бренда"]
    required_tokens = _required_match_tokens(product)
    candidate_tokens = candidate_tokens_for_line
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


def _near_miss_confidence_for_candidate(product: Dict[str, Any], title: str, sku: str, brand: str = "") -> Tuple[float, List[str]]:
    product_profile = _variant_profile(product.get("title"))
    candidate_profile = _variant_profile(f"{brand} {title}")
    for key, label in (
        ("model", "модели"),
        ("memory", "памяти"),
        ("color", "цвета"),
        ("region", "региона"),
    ):
        product_value = product_profile.get(key)
        candidate_value = candidate_profile.get(key)
        if product_value and candidate_value and product_value != candidate_value:
            return 0.0, [f"конфликт {label}: PIM={product_value}, candidate={candidate_value}"]

    product_title = _norm_match_text(product.get("title"))
    product_tokens = _match_tokens(product_title)
    candidate_tokens = _match_tokens(f"{brand} {title}")
    line_conflict = _apple_line_conflict(product_tokens, candidate_tokens)
    if line_conflict:
        return 0.0, [line_conflict]
    product_brand_tokens = _brand_tokens(product.get("title"))
    candidate_brand_tokens = _brand_tokens(brand) | _brand_tokens(title)
    if product_brand_tokens and candidate_brand_tokens and product_brand_tokens.isdisjoint(candidate_brand_tokens):
        return 0.0, ["конфликт бренда"]

    required_tokens = _required_match_tokens(product)
    missing_required = sorted(required_tokens - candidate_tokens)
    sim_missing = [token for token in missing_required if token in {"esim", "sim"}]
    if missing_required and missing_required != sim_missing:
        return 0.0, [f"нет обязательных токенов: {', '.join(missing_required)}"]
    product_sim = product_profile.get("sim") or "unknown"
    candidate_sim = candidate_profile.get("sim") or "unknown"
    if product_sim != "unknown" and candidate_sim != "unknown" and product_sim != candidate_sim:
        return 0.79, [f"проверь SIM: PIM={product_sim}, candidate={candidate_sim}"]
    if not sim_missing:
        return 0.0, ["нет причины для ручной проверки"]

    comparable_product_tokens = {token for token in product_tokens if token not in {"esim", "sim"} and len(token) > 1}
    overlap = len(comparable_product_tokens & candidate_tokens) / max(1, len(comparable_product_tokens))
    if overlap < 0.72:
        return 0.0, [f"название похоже только на {round(overlap * 100)}%"]
    return 0.79, [f"проверь SIM: у карточки re-store не указан {'/'.join(sim_missing)}", f"название похоже на {round(overlap * 100)}%"]


def _manual_review_confidence_for_candidate(product: Dict[str, Any], title: str, sku: str, brand: str = "") -> Tuple[float, List[str]]:
    product_profile = _variant_profile(product.get("title"))
    candidate_profile = _variant_profile(f"{brand} {title}")
    product_model = product_profile.get("model")
    candidate_model = candidate_profile.get("model")
    if not product_model or not candidate_model or product_model != candidate_model:
        return 0.0, ["другая модель"]

    product_tokens = _match_tokens(_norm_match_text(product.get("title")))
    candidate_tokens = _match_tokens(f"{brand} {title}")
    line_conflict = _apple_line_conflict(product_tokens, candidate_tokens)
    if line_conflict:
        return 0.0, [line_conflict]
    product_brand_tokens = _brand_tokens(product.get("title"))
    candidate_brand_tokens = _brand_tokens(brand) | _brand_tokens(title)
    if product_brand_tokens and candidate_brand_tokens and product_brand_tokens.isdisjoint(candidate_brand_tokens):
        return 0.0, ["конфликт бренда"]

    conflicts: List[str] = []
    for key, label in (
        ("memory", "памяти"),
        ("color", "цвета"),
        ("sim", "SIM"),
        ("region", "региона"),
    ):
        product_value = product_profile.get(key)
        candidate_value = candidate_profile.get(key)
        if product_value and candidate_value and product_value != candidate_value:
            conflicts.append(f"конфликт {label}: PIM={product_value}, candidate={candidate_value}")
    if conflicts:
        return 0.0, conflicts
    return 0.0, ["нет отличий для ручной проверки"]


def _source_value_key(value: Any) -> str:
    normalized = str(value or "").lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", normalized).strip()


_COMPETITOR_SPEC_ALIASES: Dict[str, List[str]] = {
    "тип sim карты": ["количество sim карт", "sim карта", "тип sim", "sim"],
    "sim карта": ["количество sim карт", "тип sim карты", "sim"],
    "sim": ["количество sim карт", "sim карта", "тип sim карты"],
    "память": ["встроенная память", "объем встроенной памяти", "объём встроенной памяти", "накопитель", "rom"],
    "объем оперативной памяти": ["оперативная память", "ram", "озу"],
    "объем встроенной памяти": ["встроенная память", "память", "накопитель", "rom"],
    "цвет": ["название цвета от производителя", "цвет товара", "цвет корпуса"],
    "серия": ["линейка", "модельный ряд"],
    "в комплекте": ["подробная комплектация", "комплектация"],
    "страна производителя": ["страна производства"],
    "гарантия мес": ["гарантийный срок", "гарантия"],
    "гарантия": ["гарантийный срок"],
    "тип разблокировки": ["аутентификация", "разблокировка"],
    "поддержка magsafe": ["функции зарядки", "зарядка"],
    "защита от воды": ["степень защиты", "уровень защиты от влаги", "влагозащита"],
    "вес": ["вес устройства", "вес устройства г", "вес товара", "вес г"],
    "вес г": ["вес", "вес устройства", "вес устройства г", "вес товара"],
    "диагональ": ["диагональ экрана"],
    "размер изображения": ["разрешение экрана"],
    "число пикселей на дюйм ppi": ["число пикселей на дюйм"],
    "тип экрана": ["тип матрицы экрана", "тип экрана"],
    "тип дисплея": ["тип матрицы экрана", "тип экрана"],
    "интерфейсы": ["беспроводные интерфейсы"],
    "сотовая и беспроводная сеть": ["беспроводные интерфейсы", "стандарт связи"],
    "спутниковая навигация": ["навигационная система"],
    "навигация": ["навигационная система", "спутниковая навигация"],
    "стандарт": ["стандарт связи"],
    "тыловая фотокамера": ["разрешение основной камеры", "характеристики основной камеры"],
    "разрешение камеры": ["разрешение основной камеры", "характеристики основной камеры"],
    "функции тыловой фотокамеры": ["функции камеры"],
    "технологии камеры": ["функции камеры", "характеристики основной камеры"],
    "тип объектива": ["характеристики основной камеры"],
    "разрешение видео": ["максимальное разрешение видеосъемки", "видеосъемка основная камера"],
    "разъем": ["тип разъема для зарядки"],
    "зарядка": ["функции зарядки"],
    "комплектация": ["подробная комплектация"],
    "уровень защиты от влаги": ["степень защиты"],
    "материал": ["материал корпуса", "материал"],
    "материал корпуса": ["материал"],
    "датчики": ["датчики", "сенсоры"],
    "яркость": ["максимальная яркость", "яркость экрана"],
    "максимальная яркость": ["яркость", "яркость экрана"],
    "контрастность": ["контрастность экрана"],
    "тип аккумулятора": ["аккумулятор", "тип аккумулятора"],
    "аккумулятор": ["крепление аккумулятора"],
    "воспроизведение аудио": ["время работы в режиме прослушивания музыки"],
    "время работы в режиме прослушивания музыки": ["воспроизведение аудио"],
    "воспроизведение видео": ["время в режиме воспроизведения видео", "время работы в режиме воспроизведения видео", "проигрывание видео"],
    "проигрывание видео": ["воспроизведение видео", "время в режиме воспроизведения видео", "время работы в режиме воспроизведения видео"],
    "страна производства": ["страна производителя"],
    "высота мм": ["высота устройства мм", "длина устройства мм", "высота"],
    "высота": ["высота устройства мм", "длина устройства мм"],
    "ширина мм": ["ширина устройства мм", "ширина"],
    "ширина": ["ширина устройства мм"],
    "толщина мм": ["толщина"],
}


def _cleanup_misplaced_competitor_values(features: List[Dict[str, Any]]) -> None:
    battery_mount_values = {"несъемный", "несъемная", "несъёмный", "несъёмная", "съемный", "съёмный"}
    for feature in features:
        normalized_name = _source_value_key(feature.get("name") or feature.get("code"))
        if "емкость аккумулятора" not in normalized_name:
            continue
        value_key = _source_value_key(feature.get("value"))
        if value_key not in battery_mount_values:
            continue
        feature["value"] = ""
        source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
        competitor_values = source_values.get("competitor") if isinstance(source_values.get("competitor"), dict) else {}
        for source_id, payload in list(competitor_values.items()):
            if isinstance(payload, dict) and _source_value_key(payload.get("raw_value")) in battery_mount_values:
                competitor_values.pop(source_id, None)
        if competitor_values:
            source_values["competitor"] = competitor_values
            feature["source_values"] = source_values
        else:
            source_values.pop("competitor", None)
            if source_values:
                feature["source_values"] = source_values
            else:
                feature.pop("source_values", None)


def _feature_lookup_keys(name: Any) -> List[str]:
    base = _source_value_key(name)
    if not base:
        return []
    keys = [base]
    keys.extend(_COMPETITOR_SPEC_ALIASES.get(base, []))
    # Store77 and re-store often omit the "экрана/устройства" suffix.
    if base.endswith(" экрана"):
        keys.append(base.removesuffix(" экрана").strip())
    if base.endswith(" устройства"):
        keys.append(base.removesuffix(" устройства").strip())
    out: List[str] = []
    seen: set[str] = set()
    for key in keys:
        normalized = _source_value_key(key)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _find_feature_for_source_name(
    feature_by_key: Dict[str, Dict[str, Any]],
    source_name: Any,
) -> Optional[Dict[str, Any]]:
    for key in _feature_lookup_keys(source_name):
        feature = feature_by_key.get(key)
        if feature:
            return feature
    return None


def _confirmed_links_for_product(discovery: Dict[str, Any], product_id: str) -> List[Dict[str, Any]]:
    normalized_product_id = str(product_id or "").strip()
    out: List[Dict[str, Any]] = []
    for link in (discovery.get("links") or {}).values():
        if not isinstance(link, dict):
            continue
        if str(link.get("product_id") or "").strip() != normalized_product_id:
            continue
        if str(link.get("status") or "").strip() not in {"confirmed", "approved"}:
            continue
        source_id = str(link.get("source_id") or "").strip()
        url = str(link.get("url") or "").strip()
        if source_id in ALLOWED_SITES and url and detect_site(url) == source_id:
            out.append({**link, "source_id": source_id, "url": url})
    try:
        for link in list_pim_channel_links(
            scope="competitor_product",
            entity_type="product",
            entity_id=normalized_product_id,
            status="confirmed",
        ):
            provider = str(link.get("provider") or "").strip()
            url = str(link.get("url") or "").strip()
            if provider not in ALLOWED_SITES or not url or detect_site(url) != provider:
                continue
            key = f"{normalized_product_id}:{provider}"
            if any(str(item.get("id") or "") == key or str(item.get("source_id") or "") == provider for item in out):
                continue
            payload = link.get("payload") if isinstance(link.get("payload"), dict) else {}
            out.append(
                {
                    "id": key,
                    "product_id": normalized_product_id,
                    "source_id": provider,
                    "candidate_id": payload.get("candidate_id") or link.get("link_id"),
                    "url": url,
                    "status": "confirmed",
                    "confirmed_at": link.get("updated_at") or payload.get("confirmed_at"),
                    "last_checked_at": payload.get("last_checked_at") or link.get("updated_at"),
                    "source": link.get("source") or payload.get("source") or "channel_link",
                }
            )
    except Exception:
        # JSON discovery remains the compatibility source when relational storage
        # is unavailable in isolated tests or during partial migrations.
        pass
    return out


def _candidate_from_channel_link(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    provider = str(row.get("provider") or "").strip()
    product_id = str(row.get("entity_id") or "").strip()
    if provider not in ALLOWED_SITES or not product_id:
        return None
    link_id = str(row.get("link_id") or "").strip()
    if link_id.endswith(":scan") or str(row.get("source") or "").strip() == "discovery_scan":
        return None
    if str(row.get("status") or "").strip() == "confirmed" and link_id == f"{product_id}:{provider}":
        # Product-source confirmed links are the accepted result, not another
        # candidate row. Candidate rows keep their discovery candidate id.
        return None
    url = str(row.get("url") or "").strip()
    if not url:
        return None
    source_name = next((str(item.get("name") or "") for item in DISCOVERY_SOURCES if item.get("id") == provider), provider)
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    status = {
        "candidate": "needs_review",
        "confirmed": "approved",
        "approved": "approved",
        "rejected": "rejected",
        "stale": "stale",
    }.get(str(row.get("status") or "").strip(), str(payload.get("raw_status") or row.get("status") or "needs_review"))
    return {
        "id": str(payload.get("candidate_id") or link_id or "").strip(),
        "product_id": product_id,
        "source_id": provider,
        "source_name": source_name,
        "url": url,
        "title": str(row.get("title") or "").strip(),
        "status": status,
        "confidence_score": row.get("score"),
        "confidence_reasons": payload.get("confidence_reasons") if isinstance(payload.get("confidence_reasons"), list) else [],
        "category_id": str(payload.get("category_id") or "").strip(),
        "product_title": str(payload.get("product_title") or "").strip(),
        "product_sku": str(payload.get("product_sku") or "").strip(),
        "match_group_key": str(payload.get("match_group_key") or "").strip(),
        "product_sim_profile": str(payload.get("product_sim_profile") or "").strip(),
        "candidate_sim_profile": str(payload.get("candidate_sim_profile") or "").strip(),
        "profile_text": str(payload.get("profile_text") or "").strip(),
        "profile_specs": payload.get("profile_specs") if isinstance(payload.get("profile_specs"), dict) else {},
        "last_seen_at": payload.get("last_seen_at") or row.get("updated_at"),
        "reviewed_at": payload.get("reviewed_at"),
        "rejection_reason": payload.get("rejection_reason"),
        "source": str(row.get("source") or "channel_link"),
    }


def _link_from_channel_link(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    provider = str(row.get("provider") or "").strip()
    product_id = str(row.get("entity_id") or "").strip()
    url = str(row.get("url") or "").strip()
    if provider not in ALLOWED_SITES or not product_id or not url or detect_site(url) != provider:
        return None
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    return {
        "id": f"{product_id}:{provider}",
        "product_id": product_id,
        "source_id": provider,
        "candidate_id": payload.get("candidate_id") or row.get("link_id"),
        "url": url,
        "status": "confirmed",
        "confirmed_at": payload.get("confirmed_at") or row.get("updated_at"),
        "last_checked_at": payload.get("last_checked_at") or row.get("updated_at"),
        "source": row.get("source") or payload.get("source") or "channel_link",
    }


def _candidate_confidence_score(candidate: Dict[str, Any]) -> float:
    try:
        return max(0.0, min(1.0, float(candidate.get("confidence_score") or 0.0)))
    except Exception:
        return 0.0


def _is_actionable_product_candidate(candidate: Dict[str, Any]) -> bool:
    status = str(candidate.get("status") or "").strip()
    if status == "approved":
        return True
    if status == "needs_review":
        return _candidate_confidence_score(candidate) >= _ACTIONABLE_DISCOVERY_CONFIDENCE_SCORE
    return False


def _is_visible_product_candidate(candidate: Dict[str, Any]) -> bool:
    status = str(candidate.get("status") or "").strip()
    if status == "approved":
        return True
    if status == "needs_review":
        return _candidate_confidence_score(candidate) >= _VISIBLE_DISCOVERY_CONFIDENCE_SCORE
    return False


def _persist_product_source_scan_state(
    product_id: str,
    source_id: str,
    *,
    status: str,
    run_id: str,
    message: str = "",
    error: Optional[str] = None,
    candidates_count: int = 0,
) -> None:
    normalized_product_id = str(product_id or "").strip()
    normalized_source_id = str(source_id or "").strip()
    if not normalized_product_id or normalized_source_id not in ALLOWED_SITES:
        return
    payload = {
        "source_id": normalized_source_id,
        "run_id": str(run_id or "").strip(),
        "last_scanned_at": now_iso(),
        "message": str(message or "").strip(),
        "error": str(error or "").strip(),
        "candidates_count": max(0, int(candidates_count or 0)),
    }
    upsert_pim_channel_link(
        {
            "link_id": _source_scan_link_id(normalized_product_id, normalized_source_id),
            "scope": "competitor_product",
            "entity_type": "product",
            "entity_id": normalized_product_id,
            "provider": normalized_source_id,
            "status": status,
            "source": "discovery_scan",
            "payload": payload,
        }
    )


def _product_source_scan_states(product_id: str) -> Dict[str, Dict[str, Any]]:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        return {}
    states: Dict[str, Dict[str, Any]] = {}
    try:
        rows = list_pim_channel_links(
            scope="competitor_product",
            entity_type="product",
            entity_id=normalized_product_id,
        )
    except Exception:
        return states
    for row in rows:
        if str(row.get("source") or "").strip() != "discovery_scan":
            continue
        source_id = str(row.get("provider") or "").strip()
        if source_id not in ALLOWED_SITES:
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        states[source_id] = {
            "source_id": source_id,
            "status": str(row.get("status") or "").strip(),
            "updated_at": row.get("updated_at"),
            "last_scanned_at": payload.get("last_scanned_at") or row.get("updated_at"),
            "message": str(payload.get("message") or "").strip(),
            "error": str(payload.get("error") or "").strip(),
            "run_id": str(payload.get("run_id") or "").strip(),
            "candidates_count": int(payload.get("candidates_count") or 0),
        }
    return states


def _product_discovery_source_summaries(
    product_id: str,
    candidates: List[Dict[str, Any]],
    confirmed_links: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized_product_id = str(product_id or "").strip()
    scan_states = _product_source_scan_states(normalized_product_id)
    summaries: List[Dict[str, Any]] = []
    for source in DISCOVERY_SOURCES:
        source_id = str(source.get("id") or "").strip()
        source_candidates = [
            item
            for item in candidates
            if str(item.get("product_id") or "").strip() == normalized_product_id
            and str(item.get("source_id") or "").strip() == source_id
        ]
        source_links = [
            link
            for link in confirmed_links
            if str(link.get("source_id") or "").strip() == source_id
        ]
        actionable = [item for item in source_candidates if _is_actionable_product_candidate(item)]
        visible = [item for item in source_candidates if _is_visible_product_candidate(item)]
        best = max(source_candidates, key=_candidate_confidence_score, default=None)
        best_score = _candidate_confidence_score(best) if best else None
        hidden_count = max(0, len(source_candidates) - len(visible))
        if source_links:
            status = "confirmed"
            label = "Подтверждено"
            message = "Источник используется для загрузки параметров, описания и медиа."
        elif actionable:
            status = "review"
            label = "Нужен выбор"
            message = "Есть кандидаты с достаточной точностью, их нужно подтвердить или отклонить."
        elif visible:
            status = "review"
            label = "Есть кандидаты"
            message = "Источник нашел похожие карточки. Их нужно подтвердить или отклонить вручную."
        elif best:
            status = "no_exact_match"
            label = "Нет точного товара"
            message = "Найденные карточки скрыты: точность ниже порога или товар не совпадает."
        elif scan_states.get(source_id, {}).get("status") == "scan_error":
            status = "scan_error"
            label = "Ошибка источника"
            message = scan_states[source_id].get("message") or "Источник не ответил или вернул ошибку. Можно повторить поиск."
        elif scan_states.get(source_id, {}).get("status") == "scanned_empty":
            status = "no_exact_match"
            label = "Нет точного товара"
            message = "Источник проверен: точной карточки для этого SKU не найдено."
        else:
            status = "empty"
            label = "Не сканировали"
            message = "По этому источнику пока нет кандидатов для SKU."
        summaries.append(
            {
                "source_id": source_id,
                "source_name": str(source.get("name") or source_id),
                "domain": str(source.get("domain") or ""),
                "status": status,
                "label": label,
                "message": message,
                "confirmed_count": len(source_links),
                "actionable_count": len(actionable),
                "hidden_count": hidden_count,
                "best_score": best_score,
                "best_title": str((best or {}).get("title") or "").strip(),
                "best_url": str((best or {}).get("url") or "").strip(),
                "best_reasons": (best or {}).get("confidence_reasons")
                if isinstance((best or {}).get("confidence_reasons"), list)
                else [],
                "last_scanned_at": scan_states.get(source_id, {}).get("last_scanned_at"),
                "scan_error": scan_states.get(source_id, {}).get("error"),
            }
        )
    return summaries


def _merge_relational_discovery_items(
    candidates: Dict[str, Any],
    links: Dict[str, Any],
    *,
    product_ids: Optional[set[str]] = None,
) -> None:
    try:
        rows = list_pim_channel_links(
            scope="competitor_product",
            entity_type="product",
            entity_ids=sorted(product_ids) if product_ids else None,
        )
    except Exception:
        return
    for row in rows:
        status = str(row.get("status") or "").strip()
        provider = str(row.get("provider") or "").strip()
        entity_id = str(row.get("entity_id") or "").strip()
        link_id = str(row.get("link_id") or "").strip()
        if status == "confirmed" and link_id == f"{entity_id}:{provider}":
            link = _link_from_channel_link(row)
            if link and str(link.get("id") or "") not in links:
                links[str(link["id"])] = link
        candidate = _candidate_from_channel_link(row)
        if candidate and str(candidate.get("id") or "").strip() and str(candidate["id"]) not in candidates:
            candidates[str(candidate["id"])] = candidate


def _relational_candidate_by_id(candidate_id: str) -> Optional[Dict[str, Any]]:
    normalized_candidate_id = str(candidate_id or "").strip()
    if not normalized_candidate_id:
        return None
    try:
        rows = list_pim_channel_links(
            link_id=normalized_candidate_id,
            scope="competitor_product",
            entity_type="product",
        )
    except Exception:
        return None
    for row in rows:
        candidate = _candidate_from_channel_link(row)
        if candidate and str(candidate.get("id") or "").strip() == normalized_candidate_id:
            return candidate
    return None


def _persist_competitor_channel_candidate(candidate: Dict[str, Any]) -> None:
    product_id = str(candidate.get("product_id") or "").strip()
    source_id = str(candidate.get("source_id") or "").strip()
    if not product_id or source_id not in ALLOWED_SITES:
        return
    status = str(candidate.get("status") or "needs_review").strip()
    channel_status = {
        "needs_review": "candidate",
        "approved": "approved",
        "rejected": "rejected",
        "stale": "stale",
    }.get(status, status or "candidate")
    try:
        upsert_pim_channel_link(
            {
                "link_id": str(candidate.get("id") or ""),
                "scope": "competitor_product",
                "entity_type": "product",
                "entity_id": product_id,
                "provider": source_id,
                "url": str(candidate.get("url") or ""),
                "external_id": str(candidate.get("sku") or candidate.get("gtin") or ""),
                "title": str(candidate.get("title") or ""),
                "status": channel_status,
                "score": candidate.get("confidence_score"),
                "source": "discovery",
                "payload": {
                    "candidate_id": candidate.get("id"),
                    "category_id": candidate.get("category_id"),
                    "product_title": candidate.get("product_title"),
                    "product_sku": candidate.get("product_sku"),
                    "match_group_key": candidate.get("match_group_key"),
                    "product_sim_profile": candidate.get("product_sim_profile"),
                    "candidate_sim_profile": candidate.get("candidate_sim_profile"),
                    "profile_text": candidate.get("profile_text"),
                    "profile_specs": candidate.get("profile_specs") if isinstance(candidate.get("profile_specs"), dict) else {},
                    "confidence_reasons": candidate.get("confidence_reasons") if isinstance(candidate.get("confidence_reasons"), list) else [],
                    "raw_status": status,
                    "reviewed_at": candidate.get("reviewed_at"),
                    "rejection_reason": candidate.get("rejection_reason"),
                    "last_seen_at": candidate.get("last_seen_at"),
                },
            }
        )
    except Exception:
        pass


def _persist_competitor_channel_link(link: Dict[str, Any], candidate: Optional[Dict[str, Any]] = None) -> None:
    product_id = str(link.get("product_id") or (candidate or {}).get("product_id") or "").strip()
    source_id = str(link.get("source_id") or (candidate or {}).get("source_id") or "").strip()
    url = str(link.get("url") or (candidate or {}).get("url") or "").strip()
    if not product_id or source_id not in ALLOWED_SITES or not url:
        return
    link_id = str(link.get("id") or f"{product_id}:{source_id}")
    existing: Dict[str, Any] = {}
    try:
        rows = list_pim_channel_links(
            link_id=link_id,
            scope="competitor_product",
            entity_type="product",
            entity_id=product_id,
        )
        existing = next((row for row in rows if isinstance(row, dict)), {})
    except Exception:
        existing = {}
    existing_payload = existing.get("payload") if isinstance(existing.get("payload"), dict) else {}
    payload = dict(existing_payload)

    def put_payload(key: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        if isinstance(value, list) and not value:
            return
        payload[key] = value

    put_payload("candidate_id", link.get("candidate_id") or (candidate or {}).get("id"))
    put_payload("category_id", (candidate or {}).get("category_id") or existing_payload.get("category_id"))
    put_payload("product_title", (candidate or {}).get("product_title") or existing_payload.get("product_title"))
    put_payload("product_sku", (candidate or {}).get("product_sku") or existing_payload.get("product_sku"))
    put_payload("match_group_key", (candidate or {}).get("match_group_key") or existing_payload.get("match_group_key"))
    put_payload("product_sim_profile", (candidate or {}).get("product_sim_profile") or existing_payload.get("product_sim_profile"))
    put_payload("candidate_sim_profile", (candidate or {}).get("candidate_sim_profile") or existing_payload.get("candidate_sim_profile"))
    put_payload("confirmed_at", link.get("confirmed_at") or existing_payload.get("confirmed_at"))
    put_payload("last_checked_at", link.get("last_checked_at") or existing_payload.get("last_checked_at"))
    put_payload("last_enriched_at", link.get("last_enriched_at") or existing_payload.get("last_enriched_at"))
    put_payload(
        "confidence_reasons",
        (candidate or {}).get("confidence_reasons") if isinstance((candidate or {}).get("confidence_reasons"), list) else existing_payload.get("confidence_reasons"),
    )

    try:
        upsert_pim_channel_link(
            {
                "link_id": link_id,
                "scope": "competitor_product",
                "entity_type": "product",
                "entity_id": product_id,
                "provider": source_id,
                "url": url,
                "external_id": str((candidate or {}).get("sku") or (candidate or {}).get("gtin") or existing.get("external_id") or ""),
                "title": str((candidate or {}).get("title") or link.get("title") or existing.get("title") or ""),
                "status": "confirmed",
                "score": (candidate or {}).get("confidence_score") if (candidate or {}).get("confidence_score") is not None else existing.get("score"),
                "source": str(link.get("source") or existing.get("source") or "moderation"),
                "payload": payload,
            }
        )
    except Exception:
        pass


async def _merge_competitor_content_into_product(
    product: Dict[str, Any],
    *,
    extracted: Dict[str, Dict[str, Any]],
    links: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    competitor_links = content.get("competitor_links") if isinstance(content.get("competitor_links"), dict) else {}
    for source_id, link in links.items():
        source_key = str(source_id or "").strip()
        if source_key not in ALLOWED_SITES or not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if not url:
            continue
        competitor_links[source_key] = {
            "source_id": source_key,
            "url": url,
            "status": "confirmed",
            "confirmed_at": link.get("confirmed_at"),
            "last_checked_at": link.get("last_checked_at"),
            "last_enriched_at": link.get("last_enriched_at"),
            "candidate_id": link.get("candidate_id"),
        }
    if competitor_links:
        content["competitor_links"] = competitor_links

    features_raw = content.get("features") if isinstance(content.get("features"), list) else []
    features: List[Dict[str, Any]] = [dict(item) for item in features_raw if isinstance(item, dict)]

    feature_by_key: Dict[str, Dict[str, Any]] = {}
    for feature in features:
        for key in (feature.get("code"), feature.get("name")):
            for normalized in _feature_lookup_keys(key):
                if normalized:
                    feature_by_key[normalized] = feature

    source_evidence = content.get("source_evidence") if isinstance(content.get("source_evidence"), dict) else {}
    competitors_evidence = source_evidence.get("competitors") if isinstance(source_evidence.get("competitors"), dict) else {}

    matched_count = 0
    unmatched_count = 0
    enriched_sources: List[str] = []
    source_values = content.get("source_values") if isinstance(content.get("source_values"), dict) else {}
    existing_images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
    if not existing_images:
        legacy_media = content.get("media") if isinstance(content.get("media"), list) else []
        existing_images = [item for item in legacy_media if isinstance(item, dict)]

    existing_store77_urls = [
        str(item.get("url") or "").strip()
        for item in existing_images
        if isinstance(item, dict)
        and str(item.get("source") or "").strip() == "store77"
        and str(item.get("url") or "").strip()
        and not _is_internal_upload_url(str(item.get("url") or "").strip())
    ]
    existing_store77_source_url = ""
    for item in existing_images:
        if isinstance(item, dict) and str(item.get("source") or "").strip() == "store77":
            existing_store77_source_url = str(item.get("source_url") or "").strip()
            if existing_store77_source_url:
                break
    existing_store77_payloads = await _fetch_store77_images_with_browser(existing_store77_urls, existing_store77_source_url) if existing_store77_source_url else {}

    for existing_image in existing_images:
        if not isinstance(existing_image, dict):
            continue
        existing_image.setdefault("role", "gallery")
        existing_image.setdefault("selected", True)
        existing_image.setdefault("status", "ready")
        current_url = str(existing_image.get("url") or "").strip()
        if not current_url or _is_internal_upload_url(current_url):
            continue
        source_id_existing = str(existing_image.get("source") or "competitor").strip() or "competitor"
        source_url_existing = str(existing_image.get("source_url") or "").strip()
        imported_existing = await _import_competitor_image_to_storage(
            image_url=current_url,
            product=product,
            source_id=source_id_existing,
            source_url=source_url_existing,
        )
        if not imported_existing and source_id_existing == "store77" and current_url in existing_store77_payloads:
            body, content_type = existing_store77_payloads[current_url]
            imported_existing = _upload_competitor_image_bytes(
                image_url=current_url,
                data=body,
                content_type=content_type,
                product=product,
                source_id=source_id_existing,
            )
        if imported_existing:
            existing_image.update(imported_existing)

    image_urls = {str(item.get("url") or "").strip() for item in existing_images if isinstance(item, dict) and str(item.get("url") or "").strip()}
    image_external_urls = {
        str(item.get("external_url") or item.get("source_image_url") or "").strip()
        for item in existing_images
        if isinstance(item, dict) and str(item.get("external_url") or item.get("source_image_url") or "").strip()
    }

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
            if normalized_name == "размеры":
                nums = re.findall(r"\d+(?:[,.]\d+)?", raw_text)
                if len(nums) >= 3:
                    dimensions = {
                        "высота устройства мм": nums[0].replace(",", "."),
                        "длина устройства мм": nums[0].replace(",", "."),
                        "ширина устройства мм": nums[1].replace(",", "."),
                        "толщина": nums[2].replace(",", "."),
                    }
                    dimension_matched = False
                    for dim_name, dim_value in dimensions.items():
                        dim_feature = _find_feature_for_source_name(feature_by_key, dim_name)
                        if not dim_feature:
                            continue
                        dimension_matched = True
                        if not str(dim_feature.get("value") or "").strip():
                            dim_feature["value"] = dim_value
                        dim_source_values = dim_feature.get("source_values") if isinstance(dim_feature.get("source_values"), dict) else {}
                        dim_competitor_values = dim_source_values.get("competitor") if isinstance(dim_source_values.get("competitor"), dict) else {}
                        dim_competitor_values[source_id] = {
                            "raw_value": raw_text,
                            "resolved_value": dim_value,
                            "canonical_value": str(dim_feature.get("value") or "").strip(),
                        }
                        dim_source_values["competitor"] = dim_competitor_values
                        dim_feature["source_values"] = dim_source_values
                        matched_specs[f"{spec_name} → {dim_name}"] = dim_value
                        matched_count += 1
                    if dimension_matched:
                        continue
            feature = _find_feature_for_source_name(feature_by_key, spec_name)
            if not feature:
                unmatched_specs[str(spec_name)] = raw_text
                unmatched_count += 1
                continue

            dict_id = dict_id_for_product_feature(product, feature.get("name") or feature.get("code") or spec_name)
            canonical_text = canonicalize_dictionary_value(dict_id, raw_text) if dict_id else raw_text
            current_feature_value = str(feature.get("value") or "").strip()
            current_canonical = canonicalize_dictionary_value(dict_id, current_feature_value) if dict_id and current_feature_value else current_feature_value
            if not current_feature_value or current_feature_value == raw_text or (canonical_text and current_canonical == canonical_text):
                feature["value"] = canonical_text
            feature_source_values = feature.get("source_values") if isinstance(feature.get("source_values"), dict) else {}
            competitor_values = feature_source_values.get("competitor") if isinstance(feature_source_values.get("competitor"), dict) else {}
            competitor_values[source_id] = {
                "raw_value": raw_text,
                "resolved_value": canonical_text,
                "canonical_value": canonical_text,
            }
            feature_source_values["competitor"] = competitor_values
            feature["source_values"] = feature_source_values
            matched_specs[str(spec_name)] = raw_text
            matched_count += 1

        description = str(result.get("description") or "").strip()
        if description:
            descriptions = source_values.get("descriptions") if isinstance(source_values.get("descriptions"), dict) else {}
            descriptions[source_id] = {
                "site": source_id,
                "url": str((links.get(source_id) or {}).get("url") or "").strip(),
                "value": description,
                "updated_at": now_iso(),
            }
            source_values["descriptions"] = descriptions
            if not str(content.get("description") or "").strip():
                content["description"] = description

        images = result.get("images") if isinstance(result.get("images"), list) else []
        source_url = str((links.get(source_id) or {}).get("url") or "").strip()
        current_source_image_urls = {
            str((image.get("url") if isinstance(image, dict) else image) or "").strip()
            for image in images
            if str((image.get("url") if isinstance(image, dict) else image) or "").strip()
        }
        if current_source_image_urls:
            existing_images = [
                item
                for item in existing_images
                if not (
                    isinstance(item, dict)
                    and str(item.get("source") or "").strip() == source_id
                    and str(item.get("url") or item.get("external_url") or "").strip()
                    and str(item.get("external_url") or item.get("url") or "").strip() not in current_source_image_urls
                )
            ]
            image_urls = {str(item.get("url") or "").strip() for item in existing_images if isinstance(item, dict) and str(item.get("url") or "").strip()}
            image_external_urls = {
                str(item.get("external_url") or item.get("source_image_url") or "").strip()
                for item in existing_images
                if isinstance(item, dict) and str(item.get("external_url") or item.get("source_image_url") or "").strip()
            }
        browser_image_payloads: Dict[str, Tuple[bytes, str]] = {}
        if source_id == "store77" and source_url and s3_enabled():
            pending_urls: List[str] = []
            for image in images:
                pending_url = str((image.get("url") if isinstance(image, dict) else image) or "").strip()
                if pending_url:
                    pending_urls.append(pending_url)
            browser_image_payloads = await _fetch_store77_images_with_browser(pending_urls, source_url)

        appended_images = 0
        for image in images:
            if isinstance(image, dict):
                image_url = str(image.get("url") or "").strip()
                next_image = dict(image)
            else:
                image_url = str(image or "").strip()
                next_image = {"url": image_url}
            if not image_url or image_url in image_urls or image_url in image_external_urls:
                continue
            imported_image = await _import_competitor_image_to_storage(
                image_url=image_url,
                product=product,
                source_id=source_id,
                source_url=source_url,
            )
            if not imported_image and image_url in browser_image_payloads:
                body, content_type = browser_image_payloads[image_url]
                imported_image = _upload_competitor_image_bytes(
                    image_url=image_url,
                    data=body,
                    content_type=content_type,
                    product=product,
                    source_id=source_id,
                )
            if imported_image:
                next_image.update(imported_image)
            else:
                # Broken external hotlinks must not be treated as ready media.
                continue
            next_image.setdefault("source", source_id)
            next_image.setdefault("source_url", source_url)
            next_image.setdefault("role", "gallery")
            next_image.setdefault("selected", True)
            next_image.setdefault("status", "ready")
            existing_images.append(next_image)
            image_urls.add(image_url)
            image_urls.add(str(next_image.get("url") or "").strip())
            image_external_urls.add(image_url)
            appended_images += 1
        if appended_images:
            media_sources = source_values.get("media_images") if isinstance(source_values.get("media_images"), dict) else {}
            media_sources[source_id] = {
                "site": source_id,
                "url": str((links.get(source_id) or {}).get("url") or "").strip(),
                "count": appended_images,
                "updated_at": now_iso(),
            }
            source_values["media_images"] = media_sources

        competitors_evidence[source_id] = {
            "source_id": source_id,
            "url": str((links.get(source_id) or {}).get("url") or "").strip(),
            "extracted_at": now_iso(),
            "images": result.get("images") if isinstance(result.get("images"), list) else [],
            "description": str(result.get("description") or "").strip(),
            "matched_specs": matched_specs,
            "unmatched_specs": unmatched_specs,
        }

    _cleanup_misplaced_competitor_values(features)
    content["features"] = features
    if existing_images:
        content["media_images"] = existing_images
        content["media"] = existing_images
    if source_values:
        content["source_values"] = source_values
    source_evidence["competitors"] = competitors_evidence
    content["source_evidence"] = source_evidence
    product["content"] = content
    return {
        "product": product,
        "matched_count": matched_count,
        "unmatched_count": unmatched_count,
        "enriched_sources": enriched_sources,
    }


def _compact_ai_text(value: Any, limit: int = 240) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _product_ai_targets(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    features = content.get("features") if isinstance(content.get("features"), list) else []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _append(code: Any, name: Any, source: str) -> None:
        title = str(name or code or "").strip()
        if not title:
            return
        normalized_code = str(code or _source_value_key(title) or title).strip()
        key = _source_value_key(normalized_code) or _source_value_key(title)
        if not key or key in seen:
            return
        seen.add(key)
        out.append(
            {
                "code": normalized_code,
                "name": title,
                "source": source,
                "keys": _feature_lookup_keys(title) + _feature_lookup_keys(normalized_code),
            }
        )

    for feature in features:
        if not isinstance(feature, dict):
            continue
        _append(feature.get("code"), feature.get("name") or feature.get("code"), "product")

    category_id = str(product.get("category_id") or "").strip()
    template_id, _template_category_id = _resolve_template_for_category(category_id)
    if template_id:
        for field in _master_fields(template_id):
            if not isinstance(field, dict):
                continue
            _append(field.get("code"), field.get("name") or field.get("code"), "model")

    return out


def _collect_unmatched_competitor_specs(product: Dict[str, Any]) -> List[Dict[str, str]]:
    content = product.get("content") if isinstance(product.get("content"), dict) else {}
    source_evidence = content.get("source_evidence") if isinstance(content.get("source_evidence"), dict) else {}
    competitors = source_evidence.get("competitors") if isinstance(source_evidence.get("competitors"), dict) else {}
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    for source_id, payload in competitors.items():
        if str(source_id or "").strip() not in ALLOWED_SITES or not isinstance(payload, dict):
            continue
        unmatched = payload.get("unmatched_specs") if isinstance(payload.get("unmatched_specs"), dict) else {}
        for source_name, raw_value in unmatched.items():
            name = _compact_ai_text(source_name, 120)
            value = _compact_ai_text(raw_value, 260)
            if not name or not value:
                continue
            key = f"{source_id}:{_source_value_key(name)}:{_source_value_key(value)}"
            if key in seen:
                continue
            seen.add(key)
            out.append({"source_id": str(source_id), "source_name": name, "raw_value": value})
    return out


def _noise_spec_name(name: str) -> bool:
    key = _source_value_key(name)
    if not key:
        return True
    noise_tokens = {
        "акции",
        "доставка",
        "доступность",
        "избранное",
        "кредит",
        "отзывы",
        "похожие товары",
        "покупатели",
        "рассрочка",
        "скидка",
        "цена",
    }
    return any(token in key for token in noise_tokens)


def _target_match_score(source_name: str, target: Dict[str, Any]) -> float:
    source_keys = set(_feature_lookup_keys(source_name))
    target_keys = {_source_value_key(item) for item in (target.get("keys") or []) if _source_value_key(item)}
    target_keys.add(_source_value_key(target.get("name")))
    target_keys.add(_source_value_key(target.get("code")))
    target_keys.discard("")
    if source_keys & target_keys:
        return 0.98

    source_tokens = {token for token in (_source_value_key(source_name) or "").split() if len(token) >= 3}
    target_tokens = {token for token in (_source_value_key(target.get("name")) or "").split() if len(token) >= 3}
    if not source_tokens or not target_tokens:
        return 0.0

    if "упаковк" in " ".join(target_tokens) and "упаковк" not in " ".join(source_tokens):
        return 0.0
    overlap = len(source_tokens & target_tokens)
    if overlap <= 0:
        return 0.0
    return min(0.92, overlap / max(len(source_tokens), len(target_tokens)) + 0.25)


def _rule_ai_suggestion(spec: Dict[str, str], targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    source_name = spec["source_name"]
    if _noise_spec_name(source_name):
        action = "ignore"
        best: Optional[Dict[str, Any]] = None
        score = 0.3
        reason = "похоже на служебный или маркетинговый блок, не характеристика товара"
    else:
        scored = sorted(
            ((_target_match_score(source_name, target), target) for target in targets),
            key=lambda item: item[0],
            reverse=True,
        )
        score, best = scored[0] if scored else (0.0, None)
        if best and score >= 0.72:
            action = "map_existing"
            reason = "название похоже на существующее поле модели или товара"
        else:
            action = "create_attribute"
            reason = "похожего глобального поля не найдено, нужно рассмотреть создание атрибута"

    source_id = spec["source_id"]
    item: Dict[str, Any] = {
        "id": hashlib.sha1(f"{source_id}:{source_name}:{spec['raw_value']}".encode("utf-8")).hexdigest()[:16],
        "source_id": source_id,
        "source_name": source_name,
        "raw_value": spec["raw_value"],
        "action": action,
        "confidence": round(float(score or 0.0), 2),
        "reason": reason,
        "status": "draft",
    }
    if action == "map_existing" and best:
        item["target_code"] = best.get("code")
        item["target_name"] = best.get("name")
        item["target_source"] = best.get("source")
    if action == "create_attribute":
        item["target_name"] = source_name
        item["target_code"] = _source_value_key(source_name).replace(" ", "_")
    return item


def _json_object_from_text(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _validate_llm_suggestions(
    *,
    raw_items: Any,
    rule_items: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return rule_items

    target_by_name = {_source_value_key(target.get("name")): target for target in targets}
    target_by_code = {_source_value_key(target.get("code")): target for target in targets}
    rule_by_key = {
        f"{item.get('source_id')}:{_source_value_key(item.get('source_name'))}:{_source_value_key(item.get('raw_value'))}": item
        for item in rule_items
    }
    out: List[Dict[str, Any]] = []
    used: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("source_id") or "").strip()
        source_name = _compact_ai_text(raw.get("source_name"), 120)
        raw_value = _compact_ai_text(raw.get("raw_value"), 260)
        key = f"{source_id}:{_source_value_key(source_name)}:{_source_value_key(raw_value)}"
        base = rule_by_key.get(key)
        if not base:
            continue
        used.add(key)
        action = str(raw.get("action") or base.get("action") or "").strip()
        if action not in _AI_SPEC_ACTIONS:
            action = str(base.get("action") or "create_attribute")
        next_item = dict(base)
        next_item["action"] = action
        next_item["reason"] = _compact_ai_text(raw.get("reason") or base.get("reason"), 180)
        try:
            next_item["confidence"] = max(0.0, min(1.0, float(raw.get("confidence"))))
        except Exception:
            next_item["confidence"] = base.get("confidence", 0.0)

        if action == "map_existing":
            target_key = _source_value_key(raw.get("target_code"))
            target = target_by_code.get(target_key) if target_key else None
            if not target:
                target = target_by_name.get(_source_value_key(raw.get("target_name")))
            if not target:
                target = target_by_code.get(_source_value_key(base.get("target_code"))) or target_by_name.get(_source_value_key(base.get("target_name")))
            if not target:
                next_item["action"] = "create_attribute"
                next_item["target_name"] = source_name
                next_item["target_code"] = _source_value_key(source_name).replace(" ", "_")
            else:
                next_item["target_code"] = target.get("code")
                next_item["target_name"] = target.get("name")
                next_item["target_source"] = target.get("source")
        elif action == "create_attribute":
            next_item["target_name"] = _compact_ai_text(raw.get("target_name") or source_name, 120)
            next_item["target_code"] = _source_value_key(next_item["target_name"]).replace(" ", "_")
            next_item.pop("target_source", None)
        else:
            next_item.pop("target_code", None)
            next_item.pop("target_name", None)
            next_item.pop("target_source", None)
        out.append(next_item)

    for key, item in rule_by_key.items():
        if key not in used:
            out.append(item)
    return out


async def _competitor_ai_suggestion_items(product: Dict[str, Any]) -> Dict[str, Any]:
    targets = _product_ai_targets(product)
    specs = _collect_unmatched_competitor_specs(product)
    rule_items = [_rule_ai_suggestion(spec, targets) for spec in specs]
    warnings: List[str] = []
    if not specs:
        return {"mode": "empty", "items": [], "warnings": warnings}

    product_title = _compact_ai_text(product.get("title") or product.get("name") or product.get("sku_gt") or product.get("id"), 160)
    target_payload = [{"code": item["code"], "name": item["name"]} for item in targets[:90]]
    spec_payload = specs[:45]
    system_prompt = (
        "Ты PIM-ассистент для контент-менеджера. Нужно разобрать характеристики конкурентов, "
        "которые не попали в поля товара. Ничего не придумывай сверх входных данных. "
        "Верни только JSON без Markdown."
    )
    user_prompt = (
        "Задача: для каждой характеристики конкурента выбери действие:\n"
        "map_existing — если это то же самое, что существующее поле PIM;\n"
        "create_attribute — если полезная товарная характеристика, но поля еще нет;\n"
        "ignore — если это цена, доставка, отзывы, промо или не характеристика товара.\n\n"
        f"Товар: {product_title}\n"
        f"Существующие поля PIM JSON:\n{json.dumps(target_payload, ensure_ascii=False)}\n\n"
        f"Незамапленные характеристики JSON:\n{json.dumps(spec_payload, ensure_ascii=False)}\n\n"
        "Ответ строго в формате: "
        '{"items":[{"source_id":"restore","source_name":"...","raw_value":"...","action":"map_existing|create_attribute|ignore","target_code":"...","target_name":"...","confidence":0.0,"reason":"коротко"}]}'
    )
    try:
        llm_response = await llm_chat_text(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            profile="fast",
            temperature=0.1,
            timeout_seconds=45.0,
        )
        parsed = _json_object_from_text(llm_response["content"])
        items = _validate_llm_suggestions(raw_items=parsed.get("items"), rule_items=rule_items, targets=targets)
        return {"mode": "llm", "model": llm_response.get("model"), "items": items, "warnings": warnings}
    except LlmError as exc:
        warnings.append(str(exc))
    except Exception as exc:
        warnings.append(f"AI_PARSE_ERROR:{exc.__class__.__name__}")
    return {"mode": "rules", "items": rule_items, "warnings": warnings}


def _extract_restore_search_candidates(html: str, product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not html:
        return []
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _json_string(value: Any) -> str:
        raw = html_lib.unescape(str(value or "").strip())
        if not raw:
            return ""
        try:
            decoded = json.loads(f'"{raw}"')
            return str(decoded or "").strip()
        except Exception:
            return raw.replace('\\"', '"').replace("\\/", "/").strip()

    def _last_json_field(fragment: str, key: str) -> str:
        normalized = str(fragment or "").replace('\\"', '"')
        rx = re.compile(rf'"{re.escape(key)}"\s*:\s*"(?P<value>[^"]*)"', re.IGNORECASE | re.DOTALL)
        values = [m.group("value") for m in rx.finditer(normalized)]
        return _json_string(values[-1]) if values else ""

    def _add_candidate(url: str, title: str, sku: str = "", brand: str = "", price: Any = None) -> None:
        if not url or detect_site(url) != "restore" or url in seen:
            return
        title_clean = _json_string(title)
        sku_clean = _json_string(sku)
        brand_clean = _json_string(brand)
        confidence_score, reasons = _confidence_for_candidate(product, title_clean, sku_clean, brand_clean)
        if confidence_score < 0.78:
            confidence_score, reasons = _near_miss_confidence_for_candidate(product, title_clean, sku_clean, brand_clean)
        if confidence_score < 0.78:
            confidence_score, reasons = _manual_review_confidence_for_candidate(product, title_clean, sku_clean, brand_clean)
        if confidence_score < _VISIBLE_DISCOVERY_CONFIDENCE_SCORE:
            return
        seen.add(url)
        candidates.append(
            {
                "url": url,
                "title": title_clean,
                "brand": brand_clean,
                "sku": sku_clean,
                "price": str(price or "").strip() or None,
                "confidence_score": confidence_score,
                "confidence_reasons": reasons,
            }
        )

    # re-store changes payload key order often. The product object can contain
    # `categoryName/skuCode/brandName`, nested analytics, then final `name/link`.
    # Scan every catalog link and read the nearest product fields around it
    # instead of depending on one long ordered regex.
    search_docs = [
        html,
        html.replace('\\"', '"').replace("\\/", "/"),
    ]
    link_rx_list = [
        re.compile(r'(?:\\?")link(?:\\?")\s*:\s*(?:\\?")(?P<link>/catalog/[^"\\]+/?)', re.IGNORECASE),
        re.compile(r'"link"\s*:\s*"(?P<link>/catalog/[^"]+/?)(?=")', re.IGNORECASE),
    ]
    for search_doc in search_docs:
        for link_rx in link_rx_list:
            for match in link_rx.finditer(search_doc):
                link = _json_string(match.group("link"))
                url = urljoin("https://re-store.ru", link)
                window = search_doc[max(0, match.start() - 5000) : min(len(search_doc), match.end() + 1000)]
                title = _last_json_field(window, "name")
                sku = _last_json_field(window, "skuCode")
                brand = _last_json_field(window, "brandName") or _last_json_field(window, "brand")
                price = _last_json_field(window, "price")
                _add_candidate(url, title, sku, brand, price)
                if len(candidates) >= 5:
                    candidates.sort(key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
                    return candidates
    candidates.sort(key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
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


def _restore_candidate_profile_text(candidate: Dict[str, Any], specs: Dict[str, Any]) -> str:
    values = [
        candidate.get("brand"),
        candidate.get("title"),
        specs.get("Память"),
        specs.get("Цвет"),
        specs.get("SIM-карта"),
    ]
    return " ".join(str(item or "").strip() for item in values if str(item or "").strip())


async def _enrich_restore_candidate_for_review(product: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    url = str(candidate.get("url") or "").strip()
    if not url:
        return candidate
    try:
        html = await _fetch_search_html(url)
        _, specs, _ = extract_restore_product_content_from_html(html, base_url=url)
    except Exception:
        return candidate
    if not isinstance(specs, dict) or not specs:
        return candidate

    profile_text = _restore_candidate_profile_text(candidate, specs)
    if not profile_text:
        return candidate
    score, reasons = _confidence_for_candidate(product, profile_text, str(candidate.get("sku") or ""), str(candidate.get("brand") or ""))
    if score < 0.78:
        score, reasons = _near_miss_confidence_for_candidate(product, profile_text, str(candidate.get("sku") or ""), str(candidate.get("brand") or ""))
    if score < 0.78:
        score, reasons = _manual_review_confidence_for_candidate(product, profile_text, str(candidate.get("sku") or ""), str(candidate.get("brand") or ""))

    enriched = dict(candidate)
    enriched["profile_text"] = profile_text
    enriched["profile_specs"] = {
        key: str(specs.get(key) or "").strip()
        for key in ("Память", "Цвет", "SIM-карта")
        if str(specs.get(key) or "").strip()
    }
    if score >= _VISIBLE_DISCOVERY_CONFIDENCE_SCORE:
        enriched["confidence_score"] = score
        enriched["confidence_reasons"] = reasons
    return enriched


async def _enrich_restore_candidates_for_review(product: Dict[str, Any], candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    enriched = await asyncio.gather(
        *(_enrich_restore_candidate_for_review(product, candidate) for candidate in candidates),
        return_exceptions=True,
    )
    return [
        item if isinstance(item, dict) else candidates[idx]
        for idx, item in enumerate(enriched)
    ]


def _restore_iphone_direct_url(product: Dict[str, Any]) -> str:
    profile = _variant_profile(product.get("title"))
    model = str(profile.get("model") or "")
    memory = str(profile.get("memory") or "")
    color = str(profile.get("color") or "")
    model_match = re.fullmatch(r"iphone_(\d{1,2})(?:_(pro_max|pro|plus|mini))?", model)
    memory_match = re.fullmatch(r"(\d+)(gb|tb)", memory)
    model_codes = {
        "pro_max": "MAX",
        "pro": "PRO",
        "plus": "PLUS",
        "mini": "MINI",
        "": "",
    }
    color_codes = {
        "desert_titanium": "DSTN",
        "natural_titanium": "NATN",
        "white_titanium": "WHTN",
        "black_titanium": "BLKT",
        "blue": "BLUE",
        "silver": "SLVN",
        "orange": "ORNG",
    }
    if not model_match or not memory_match or color not in color_codes:
        return ""
    generation = model_match.group(1)
    suffix = model_match.group(2) or ""
    memory_code = memory_match.group(1) if memory_match.group(2) == "gb" else f"{memory_match.group(1)}TB"
    code = f"101{generation}{model_codes.get(suffix, '')}{memory_code}{color_codes[color]}"
    return f"https://re-store.ru/catalog/{code}/"


async def _restore_seed_candidates_for_product(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = _restore_iphone_direct_url(product)
    if not url:
        return []
    try:
        html = await _fetch_search_html(url)
        _, specs, _ = extract_restore_product_content_from_html(html, base_url=url)
    except Exception:
        return []
    if not isinstance(specs, dict) or not specs:
        return []
    title = str(product.get("title") or "").strip()
    profile_text = _restore_candidate_profile_text({"brand": "Apple", "title": title}, specs)
    score, reasons = _confidence_for_candidate(product, profile_text, "", "Apple")
    if score < 0.78:
        score, reasons = _near_miss_confidence_for_candidate(product, profile_text, "", "Apple")
    if score < 0.78:
        return []
    return [
        {
            "url": url,
            "title": title,
            "brand": "Apple",
            "sku": url.rstrip("/").split("/")[-1],
            "confidence_score": min(0.98, max(score, 0.89)),
            "confidence_reasons": [*reasons, "re-store URL собран из модели, памяти и цвета"],
            "profile_text": profile_text,
            "profile_specs": {
                key: str(specs.get(key) or "").strip()
                for key in ("Память", "Цвет", "SIM-карта")
                if str(specs.get(key) or "").strip()
            },
            "discovery_strategy": "restore_direct_sku_seed",
            "match_group_key": _model_memory_color_group_key(profile_text),
        }
    ]


async def _discover_restore_candidates(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if os.getenv("ENABLE_HTTP_COMPETITOR_DISCOVERY", "1").strip().lower() in {"0", "false", "no"}:
        # Hard kill switch for production incidents. re-store serves the product
        # payload in the first HTML response, so this does not require browser
        # automation and should work by default for per-SKU discovery.
        return []
    out: List[Dict[str, Any]] = await _restore_seed_candidates_for_product(product)
    seen: set[str] = set()
    for candidate in out:
        candidate_url = str(candidate.get("url") or "")
        if candidate_url:
            seen.add(candidate_url)
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
                return await _enrich_restore_candidates_for_review(product, out)
    return await _enrich_restore_candidates_for_review(product, out)


async def _discover_store77_candidates(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    if os.getenv("ENABLE_BROWSER_COMPETITOR_DISCOVERY", "1").strip().lower() in {"0", "false", "no"}:
        # Store77 renders product grids in the browser. Keep a hard kill switch
        # for production incidents, but discovery must work by default.
        return []
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    category_urls = _store77_category_urls_for_product(product)
    if not category_urls:
        # store77 search page is browser/ajax-backed and can consume one timeout
        # per SKU. For category scans we must not block the whole worker when no
        # deterministic category route is known yet.
        return []
    for url in category_urls:
        try:
            html = await _fetch_store77_category_html(url)
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
        if out:
            return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
    for term in _query_terms_for_product(product):
        url = f"https://store77.net/search/?q={quote_plus(term)}"
        try:
            html = await fetch_browser_html(url, timeout_ms=7000)
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
    if not out:
        for candidate in _store77_seed_candidates_for_product(product):
            candidate_url = str(candidate.get("url") or "")
            if not candidate_url or candidate_url in seen:
                continue
            try:
                html = await _fetch_store77_category_html(candidate_url)
            except Exception:
                continue
            if not _store77_seed_candidate_matches_page(candidate, html):
                continue
            seen.add(candidate_url)
            out.append(candidate)
            if len(out) >= 5:
                return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)
    return sorted(out, key=lambda item: float(item.get("confidence_score") or 0), reverse=True)


async def _fetch_store77_category_html(url: str) -> str:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return ""
    now = monotonic()
    cached = _store77_category_html_cache.get(normalized_url)
    if cached and now - float(cached[0] or 0.0) <= _STORE77_CATEGORY_HTML_CACHE_TTL_SECONDS:
        return cached[1]
    html = await fetch_browser_html(normalized_url, timeout_ms=10000)
    if len(_store77_category_html_cache) > 12:
        oldest_key = min(_store77_category_html_cache, key=lambda key: _store77_category_html_cache[key][0])
        _store77_category_html_cache.pop(oldest_key, None)
    _store77_category_html_cache[normalized_url] = (now, html)
    return html


def _store77_category_urls_for_product(product: Dict[str, Any]) -> List[str]:
    title = _norm_match_text(product.get("title"))
    urls: List[str] = []
    match = re.search(r"\biphone\s+(\d{1,2})(?:\s+(pro\s+max|pro|plus|mini))?", title)
    if match:
        generation = match.group(1)
        suffix = re.sub(r"\s+", "_", (match.group(2) or "").strip())
        slug = "_".join(part for part in ("apple", "iphone", generation, suffix) if part)
        if int(generation) >= 17:
            variants = [f"https://store77.net/{slug}_1/", f"https://store77.net/{slug}_2/", f"https://store77.net/{slug}/"]
        else:
            variants = [f"https://store77.net/{slug}_2/", f"https://store77.net/{slug}/", f"https://store77.net/{slug}_1/"]
        for url in variants:
            if url not in urls:
                urls.append(url)
    if "airpods" in title:
        if "pro" in title and re.search(r"\b3\b", title):
            urls.append("https://store77.net/apple_airpods_pro_3/")
        elif "max" in title and re.search(r"\b2\b", title):
            urls.append("https://store77.net/apple_airpods_max_2/")
        elif re.search(r"\b4\b", title):
            urls.append("https://store77.net/apple_airpods_4/")
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
        ("cosmic_orange", "Cosmic Orange", ("cosmic orange", "космический оранжевый", "orange", "оранжевый", "оранжев")),
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


def _store77_seed_candidate_matches_page(candidate: Dict[str, Any], html: str) -> bool:
    if not html or html.startswith("__ERROR__") or "__STATUS__:" in html[:80]:
        return False
    title_tokens = _match_tokens(candidate.get("title"))
    required = {
        token
        for token in title_tokens
        if token in _MATCH_REQUIRED_TOKENS or re.fullmatch(r"\d+(gb|tb)", token)
    }
    if "iphone" in title_tokens:
        required.update(token for token in title_tokens if re.fullmatch(r"\d{1,2}", token))
    if not required:
        return False
    html_tokens = _match_tokens(html[:250_000])
    return required.issubset(html_tokens)


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
        if not re.search(r"/(catalog/|product/|tovar/|goods?/|telefony_|apple_iphone_|apple_airpods_)", url, re.I):
            continue
        if not _store77_likely_product_link(href, text):
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


def _store77_likely_product_link(href: str, text: str) -> bool:
    parsed = urlparse(urljoin("https://store77.net", href))
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2:
        return True
    normalized_text = _norm_match_text(text)
    tokens = [token for token in normalized_text.split() if token]
    if len(path_parts) == 1 and len(tokens) >= 5:
        return bool(
            re.search(r"\b\d+\s*(gb|гб|tb|тб)\b", normalized_text)
            or "телефон" in tokens
            or "naushniki" in tokens
            or "наушники" in tokens
        )
    return False


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


def _catalog_node_by_id(category_id: str) -> Optional[Dict[str, Any]]:
    cid = str(category_id or "").strip()
    if not cid:
        return None
    for node in _catalog_nodes():
        if str((node or {}).get("id") or "").strip() == cid:
            return node
    return None


def _catalog_descendant_ids(category_id: str) -> List[str]:
    cid = str(category_id or "").strip()
    if not cid:
        return []
    nodes = _catalog_nodes()
    children_by_parent: Dict[str, List[str]] = {}
    for node in nodes:
        nid = str((node or {}).get("id") or "").strip()
        pid = str((node or {}).get("parent_id") or "").strip()
        if not nid:
            continue
        children_by_parent.setdefault(pid, []).append(nid)
    out: List[str] = []
    stack = [cid]
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        if not cur or cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children_by_parent.get(cur, []))
    return out


def _product_ids_for_category_scope(category_id: str, limit: int = 250) -> Tuple[List[Dict[str, Any]], set[str]]:
    category_ids = set(_catalog_descendant_ids(category_id) or [str(category_id or "").strip()])
    category_ids.discard("")
    products = query_products_full(category_ids=sorted(category_ids)) if category_ids else []
    items = [item for item in products if isinstance(item, dict)]
    limited = items[: max(1, int(limit or 250))]
    product_ids = {str(item.get("id") or "").strip() for item in limited if str(item.get("id") or "").strip()}
    return limited, product_ids


def _competitor_category_label(source_id: str, url: str) -> Tuple[str, str]:
    parsed = urlparse(str(url or "").strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return "Поиск по сайту", f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url
    if source_id == "store77":
        if len(path_parts) == 1:
            label = _humanize_competitor_slug(path_parts[0])
            return label or "Раздел Store77", f"{parsed.scheme}://{parsed.netloc}/{path_parts[0]}/"
        return " / ".join(_humanize_competitor_slug(part) for part in path_parts[:-1]) or path_parts[0], f"{parsed.scheme}://{parsed.netloc}/{'/'.join(path_parts[:-1])}/"
    if source_id == "restore":
        # re-store product URLs can be deep. For category-level context we keep
        # the stable path prefix and explicitly mark it as observed from products.
        prefix_parts = path_parts[:-1] if len(path_parts) > 1 else path_parts
        label = " / ".join(prefix_parts[-3:]) if prefix_parts else path_parts[0]
        href = f"{parsed.scheme}://{parsed.netloc}/{'/'.join(prefix_parts)}/" if prefix_parts else f"{parsed.scheme}://{parsed.netloc}/"
        return label or "Раздел re-store", href
    return " / ".join(path_parts[:-1] or path_parts), f"{parsed.scheme}://{parsed.netloc}/{'/'.join(path_parts[:-1] or path_parts)}/"


def _humanize_competitor_slug(slug: str) -> str:
    raw = str(slug or "").strip()
    known_labels = {
        "apple_airpods_4": "AirPods 4",
        "apple_airpods_pro_3": "AirPods Pro 3",
        "apple_airpods_max": "AirPods Max",
        "apple_airpods_max_2": "AirPods Max 2",
        "apple_iphone": "iPhone",
        "apple_iphone_16": "iPhone 16",
        "apple_iphone_16_pro": "iPhone 16 Pro",
        "apple_iphone_16_pro_max": "iPhone 16 Pro Max",
    }
    if raw in known_labels:
        return known_labels[raw]
    cleaned = re.sub(r"_2$", "", raw)
    if cleaned in known_labels:
        return known_labels[cleaned]
    parts = [part for part in re.split(r"[_\\-]+", cleaned) if part]
    if not parts:
        return ""
    acronyms = {"tv": "TV", "usb": "USB", "wi": "Wi", "fi": "Fi", "gps": "GPS", "sim": "SIM", "esim": "eSIM"}
    return " ".join(acronyms.get(part.lower(), part.capitalize()) for part in parts)


def _fallback_search_suggestion(source: Dict[str, Any], category_name: str) -> Dict[str, Any]:
    source_id = str(source.get("id") or "").strip()
    query = quote_plus(category_name or "")
    if source_id == "restore":
        url = f"https://re-store.ru/search/?q={query}" if query else "https://re-store.ru/search/"
    elif source_id == "store77":
        url = f"https://store77.net/search/?q={query}" if query else "https://store77.net/search/"
    else:
        url = str(source.get("base_url") or "")
    return {
        "id": f"{source_id}:search",
        "type": "search",
        "label": f"Поиск: {category_name or source.get('name') or source_id}",
        "url": url,
        "confidence": 0.25,
        "products_count": 0,
        "evidence": "fallback: в категории еще нет подтвержденных competitor links/candidates",
    }


def _category_query_tokens(category_name: str) -> set[str]:
    raw = re.sub(r"[^0-9a-zа-яё]+", " ", str(category_name or "").lower())
    tokens = {part for part in raw.split() if len(part) >= 3}
    synonym_map = {
        "смартфоны": {"smartfon", "smartfony", "smartphone", "iphone", "телефон", "телефоны", "telefony"},
        "телефоны": {"smartfon", "smartfony", "smartphone", "iphone", "телефон", "telefony"},
        "планшеты": {"planshet", "planshety", "ipad", "tablet"},
        "ноутбуки": {"noutbuk", "noutbuki", "macbook", "laptop"},
        "наушники": {"naushniki", "airpods", "headphones"},
        "часы": {"watch", "applewatch", "apple-watch", "smartwatch"},
        "аксессуары": {"accessories", "aksessuary", "case", "cable", "charger"},
    }
    for token in list(tokens):
        tokens.update(synonym_map.get(token, set()))
    return tokens


def _category_candidate_score(label: str, href: str, tokens: set[str]) -> float:
    haystack = re.sub(r"[^0-9a-zа-яё]+", " ", f"{label} {href}".lower())
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token and token in haystack)
    if hits <= 0:
        return 0.0
    return min(0.94, 0.45 + hits * 0.16)


async def _scan_competitor_catalog_suggestions(source: Dict[str, Any], category_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    source_id = str(source.get("id") or "").strip()
    base_url = str(source.get("base_url") or "").rstrip("/")
    if not source_id or not base_url:
        return []

    tokens = _category_query_tokens(category_name)
    query = quote_plus(category_name or "")
    scan_urls = [base_url]
    if source_id == "restore" and query:
        scan_urls.append(f"{base_url}/search/?q={query}")
    if source_id == "store77" and query:
        scan_urls.append(f"{base_url}/search/?q={query}")

    found: Dict[str, Dict[str, Any]] = {}
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(9.0, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 SmartPIM category discovery"},
    ) as client:
        for scan_url in scan_urls:
            try:
                resp = await client.get(scan_url)
                html = resp.text or ""
            except Exception:
                continue
            if not html:
                continue
            for match in re.finditer(r"(?is)<a\\b[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<body>.*?)</a>", html):
                href = html_lib.unescape(match.group("href") or "").strip()
                label = re.sub(r"<[^>]+>", " ", match.group("body") or "")
                label = html_lib.unescape(re.sub(r"\\s+", " ", label)).strip()
                if not href or not label or len(label) > 120:
                    continue
                absolute_url = urljoin(base_url + "/", href)
                if detect_site(absolute_url) != source_id:
                    continue
                parsed = urlparse(absolute_url)
                if not parsed.path or parsed.path in {"/", "/search/"}:
                    continue
                score = _category_candidate_score(label, absolute_url, tokens)
                if score <= 0:
                    continue
                key = f"{source_id}:{parsed.scheme}://{parsed.netloc}{parsed.path}"
                current = found.get(key)
                if current and float(current.get("confidence") or 0) >= score:
                    continue
                found[key] = {
                    "id": key,
                    "type": "catalog_scan",
                    "label": label,
                    "url": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
                    "confidence": round(score, 2),
                    "products_count": 0,
                    "evidence": "catalog_scan: найдено при сканировании каталога конкурента",
                    "examples": [],
                }
    return sorted(found.values(), key=lambda row: (-float(row.get("confidence") or 0), str(row.get("label") or "")))[:limit]


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
    try:
        for row in list_pim_channel_links(scope=_COMPETITOR_MAPPING_SCOPE, entity_type="template"):
            entity_id = str(row.get("entity_id") or "").strip()
            if not entity_id:
                continue
            rel_row = _relational_competitor_mapping_row("template", entity_id)
            if rel_row and _is_configured(rel_row):
                flags[entity_id] = True
    except Exception:
        pass
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
    relational_row = _relational_competitor_mapping_row("category", category_id)
    db = load_competitor_mapping_db()
    category_rows = db.get("categories") if isinstance(db.get("categories"), dict) else {}
    row = _ensure_row_shape((category_rows or {}).get(category_id) or {})
    template_id, source_category_id = _resolve_template_for_category(category_id)
    if relational_row:
        return relational_row, template_id, source_category_id
    if any((row.get("links") or {}).values()) or any((row.get("mapping_by_site") or {}).get(site) for site in ("restore", "store77")):
        return row, template_id, source_category_id
    if template_id:
        relational_template_row = _relational_competitor_mapping_row("template", template_id)
        if relational_template_row:
            return relational_template_row, template_id, source_category_id
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
    row = _relational_competitor_mapping_row("template", template_id) or _ensure_row_shape(row)

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
    tpl_rows = db.get("templates") if isinstance(db.get("templates"), dict) else {}
    current_raw = tpl_rows.get(template_id) or {}
    current = _relational_competitor_mapping_row("template", template_id) or _ensure_row_shape(current_raw)

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

    _persist_competitor_mapping_row("template", template_id, current)
    _remove_legacy_competitor_mapping_row("template", template_id)
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

    _persist_competitor_mapping_row("category", category_id, current)
    _remove_legacy_competitor_mapping_row("category", category_id)
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


@router.get("/discovery/categories/{category_id}")
async def discovery_category_context(category_id: str) -> Dict[str, Any]:
    normalized_category_id = str(category_id or "").strip()
    if not normalized_category_id:
        raise HTTPException(status_code=400, detail="category_id is required")

    node = _catalog_node_by_id(normalized_category_id)
    if not node:
        raise HTTPException(status_code=404, detail="CATEGORY_NOT_FOUND")

    products, product_ids = _product_ids_for_category_scope(normalized_category_id)
    product_by_id = {str(item.get("id") or "").strip(): item for item in products if isinstance(item, dict)}
    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates = discovery.get("candidates") if isinstance(discovery.get("candidates"), dict) else {}
    links = discovery.get("links") if isinstance(discovery.get("links"), dict) else {}
    _merge_relational_discovery_items(candidates, links, product_ids=product_ids)
    category_name = str(node.get("name") or "").strip()
    product_has_competitor_context = {
        str(item.get("product_id") or "").strip()
        for item in [*list(candidates.values()), *list(links.values())]
        if isinstance(item, dict)
        and str(item.get("product_id") or "").strip() in product_ids
        and str(item.get("source_id") or "").strip() in ALLOWED_SITES
        and (item.get("status") in {"needs_review", "approved"} or str(item.get("url") or "").strip())
    }

    source_rows: List[Dict[str, Any]] = []
    for source in DISCOVERY_SOURCES:
        source_id = str(source.get("id") or "").strip()
        source_candidates = [
            dict(item)
            for item in candidates.values()
            if isinstance(item, dict)
            and str(item.get("source_id") or "").strip() == source_id
            and str(item.get("product_id") or "").strip() in product_ids
        ]
        source_links = [
            dict(item)
            for item in links.values()
            if isinstance(item, dict)
            and str(item.get("source_id") or "").strip() == source_id
            and str(item.get("product_id") or "").strip() in product_ids
        ]
        review_candidates: List[Dict[str, Any]] = []
        for item in source_candidates:
            if item.get("status") != "needs_review":
                continue
            product = product_by_id.get(str(item.get("product_id") or "").strip())
            if product:
                score, _ = _confidence_for_candidate(product, str(item.get("title") or ""), str(item.get("sku") or ""))
                if score < 0.78:
                    continue
            review_candidates.append(item)

        grouped: Dict[str, Dict[str, Any]] = {}
        for item in [*review_candidates, *source_links]:
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            label, category_url = _competitor_category_label(source_id, url)
            key = f"{source_id}:{category_url}"
            row = grouped.setdefault(
                key,
                {
                    "id": key,
                    "type": "observed",
                    "label": label,
                    "url": category_url,
                    "confidence": 0.0,
                    "products_count": 0,
                    "evidence": "",
                    "examples": [],
                },
            )
            row["products_count"] = int(row.get("products_count") or 0) + 1
            row["confidence"] = max(float(row.get("confidence") or 0.0), float(item.get("confidence_score") or 0.0))
            title = str(item.get("title") or item.get("product_title") or "").strip()
            if title and title not in row["examples"]:
                row["examples"].append(title)
            row["evidence"] = "observed: найдено по товарам этой ветки каталога"

        suggestions = sorted(
            grouped.values(),
            key=lambda row: (-int(row.get("products_count") or 0), -float(row.get("confidence") or 0.0), str(row.get("label") or "")),
        )[:5]
        catalog_suggestions = await _scan_competitor_catalog_suggestions(source, category_name)
        known_urls = {str(item.get("url") or "").rstrip("/") for item in suggestions}
        for item in catalog_suggestions:
            if str(item.get("url") or "").rstrip("/") not in known_urls:
                suggestions.append(item)
                known_urls.add(str(item.get("url") or "").rstrip("/"))
        suggestions = sorted(
            suggestions,
            key=lambda row: (-int(row.get("products_count") or 0), -float(row.get("confidence") or 0.0), str(row.get("label") or "")),
        )[:5]
        fallback_search = None if suggestions else _fallback_search_suggestion(source, category_name)

        source_rows.append(
            {
                "id": source_id,
                "name": source.get("name"),
                "domain": source.get("domain"),
                "status": source.get("status"),
                "products_count": len(products),
                "confirmed_count": len(source_links),
                "candidates_count": len(review_candidates),
                "needs_review_count": len(review_candidates),
                "candidate_items": sorted(
                    review_candidates,
                    key=lambda row: (
                        -float(row.get("confidence_score") or 0),
                        str(row.get("title") or row.get("url") or ""),
                    ),
                )[:6],
                "suggestions": suggestions,
                "fallback_search": fallback_search,
            }
        )

    return {
        "ok": True,
        "category": {
            "id": normalized_category_id,
            "name": category_name,
            "products_count": len(products),
            "scanned_product_ids": sorted(product_ids),
            "sample_products": [
                {
                    "id": str(item.get("id") or "").strip(),
                    "title": str(item.get("title") or item.get("name") or "").strip(),
                    "sku_gt": str(item.get("sku_gt") or item.get("sku_pim") or "").strip(),
                }
                for item in sorted(
                    products,
                    key=lambda row: (
                        str(row.get("id") or "").strip() not in product_has_competitor_context,
                        str(row.get("title") or row.get("name") or ""),
                    ),
                )[:8]
                if str(item.get("id") or "").strip()
            ],
        },
        "sources": source_rows,
    }


@router.get("/discovery/candidates")
def discovery_candidates(
    status: Optional[str] = None,
    source_id: Optional[str] = None,
    product_id: Optional[str] = None,
) -> Dict[str, Any]:
    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates = discovery.get("candidates") if isinstance(discovery.get("candidates"), dict) else {}
    links = discovery.get("links") if isinstance(discovery.get("links"), dict) else {}
    _merge_relational_discovery_items(candidates, links)
    items = list(candidates.values())
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
    _merge_relational_discovery_items(candidates_map, links_map, product_ids={normalized_product_id})

    items: List[Dict[str, Any]] = []
    all_product_candidates: List[Dict[str, Any]] = []
    for item in candidates_map.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("product_id") or "").strip() != normalized_product_id:
            continue
        all_product_candidates.append(dict(item))
        if not _is_visible_product_candidate(item):
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
        "source_summaries": _product_discovery_source_summaries(
            normalized_product_id,
            all_product_candidates,
            confirmed_links,
        ),
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


def _resolve_discovery_product_ids(
    product_ids: Optional[List[str]],
    category_id: Optional[str],
    limit: int,
) -> Optional[List[str]]:
    safe_ids = [str(item or "").strip() for item in (product_ids or []) if str(item or "").strip()]
    normalized_category_id = str(category_id or "").strip()
    if normalized_category_id:
        _, category_product_ids = _product_ids_for_category_scope(normalized_category_id, limit=max(1, int(limit or 50)))
        for item in sorted(category_product_ids):
            if item and item not in safe_ids:
                safe_ids.append(item)
    return safe_ids or None


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
    links = discovery["links"]
    product_scope_ids = {str(item.get("id") or "").strip() for item in products if str(item.get("id") or "").strip()}
    _merge_relational_discovery_items(candidates, links, product_ids=product_scope_ids)
    started_at = now_iso()
    created_count = 0
    updated_count = 0
    errors: List[Dict[str, Any]] = []
    _persist_discovery_run(_run_payload(
        run_id,
        status="running",
        sources=sources,
        product_ids=product_ids,
        limit=limit,
        started_at=started_at,
    ))

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
                _persist_product_source_scan_state(
                    product_id,
                    source_id,
                    status="scan_error",
                    run_id=run_id,
                    message="Источник долго отвечает, можно повторить поиск.",
                    error="DISCOVERY_SOURCE_TIMEOUT",
                )
                errors.append(
                    {
                        "product_id": product.get("id"),
                        "source_id": source.get("id"),
                        "error": "DISCOVERY_SOURCE_TIMEOUT",
                    }
                )
                continue
            except Exception as exc:
                error_text = str(exc) or "DISCOVERY_FAILED"
                _persist_product_source_scan_state(
                    product_id,
                    source_id,
                    status="scan_error",
                    run_id=run_id,
                    message="Источник вернул ошибку, можно повторить поиск.",
                    error=error_text,
                )
                errors.append(
                    {
                        "product_id": product.get("id"),
                        "source_id": source.get("id"),
                        "error": error_text,
                    }
                )
                continue
            if not isinstance(raw_candidates, list):
                _persist_product_source_scan_state(
                    product_id,
                    source_id,
                    status="scan_error",
                    run_id=run_id,
                    message="Источник вернул некорректный ответ, можно повторить поиск.",
                    error="INVALID_DISCOVERY_RESPONSE",
                )
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
                    _persist_competitor_channel_candidate(candidates[candidate["id"]])
                    updated_count += 1
                else:
                    candidates[candidate["id"]] = candidate
                    _persist_competitor_channel_candidate(candidate)
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
                _persist_competitor_channel_candidate(existing)
                updated_count += 1
            _persist_product_source_scan_state(
                product_id,
                source_id,
                status="scanned_empty" if not seen_candidate_ids else "scanned",
                run_id=run_id,
                message="Источник проверен, точной карточки не найдено." if not seen_candidate_ids else "Источник проверен, кандидаты обновлены.",
                candidates_count=len(seen_candidate_ids),
            )

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
    _save_competitor_mapping_runs_only(db)
    _persist_discovery_run(run)
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
        _persist_discovery_run(_run_payload(
            run_id,
            status="failed",
            sources=sources,
            product_ids=product_ids,
            limit=limit,
            finished_at=now_iso(),
            errors=[{"error": str(exc) or "DISCOVERY_FAILED"}],
        ))
    finally:
        if tenant_token is not None:
            reset_current_tenant_organization_id(tenant_token)


@router.post("/discovery/run")
async def discovery_run(payload: Dict[str, Any]) -> Dict[str, Any]:
    sources, product_ids, limit = _parse_discovery_run_request(payload)
    product_ids = _resolve_discovery_product_ids(product_ids, payload.get("category_id"), limit)
    run_id = _run_id()
    current_org_id = str(current_tenant_organization_id() or "").strip()
    organization_id = current_org_id or "org_default"
    tenant_token = None if current_org_id else set_current_tenant_organization_id(organization_id)
    try:
        if bool(payload.get("background", False)):
            run = _run_payload(
                run_id,
                status="queued",
                sources=sources,
                product_ids=product_ids,
                limit=limit,
            )
            _persist_discovery_run(run)
            _start_discovery_worker_process(run_id, organization_id)
            return {"ok": True, "run": run, "created_count": 0, "updated_count": 0, "errors_count": 0}

        run = await _execute_discovery_run(run_id, sources, product_ids, limit, organization_id)
    finally:
        if tenant_token is not None:
            reset_current_tenant_organization_id(tenant_token)

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
    run = _get_discovery_run(normalized_run_id)
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
    links = discovery["links"]
    candidate = candidates.get(candidate_id)
    if not isinstance(candidate, dict):
        candidate = _relational_candidate_by_id(candidate_id)
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=404, detail="Candidate not found")
        candidates[candidate_id] = candidate
    product_id_for_merge = str(candidate.get("product_id") or "").strip()
    if product_id_for_merge:
        _merge_relational_discovery_items(candidates, links, product_ids={product_id_for_merge})
        candidate = candidates.get(candidate_id, candidate)

    reviewed_at = now_iso()
    if action == "approve":
        candidate["status"] = "approved"
        candidate["reviewed_at"] = reviewed_at
        link_key = f"{candidate.get('product_id')}:{candidate.get('source_id')}"
        confirmed_link = {
            "id": link_key,
            "product_id": candidate.get("product_id"),
            "source_id": candidate.get("source_id"),
            "candidate_id": candidate_id,
            "url": candidate.get("url"),
            "status": "confirmed",
            "confirmed_at": reviewed_at,
            "last_checked_at": candidate.get("last_seen_at") or reviewed_at,
        }
        links[link_key] = confirmed_link
        _persist_competitor_channel_link(confirmed_link, candidate)
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
                _persist_competitor_channel_candidate(sibling)
    else:
        candidate["status"] = "rejected"
        candidate["reviewed_at"] = reviewed_at
        candidate["rejection_reason"] = str(payload.get("reason") or "").strip()

    candidates[candidate_id] = candidate
    _persist_competitor_channel_candidate(candidate)
    _save_competitor_mapping_runs_only(db)
    return {"ok": True, "candidate": candidate, "links": links}


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
    candidates = discovery["candidates"]
    links = discovery["links"]
    _merge_relational_discovery_items(candidates, links, product_ids={normalized_product_id})
    reviewed_at = now_iso()
    link_key = f"{normalized_product_id}:{source_id}"
    confirmed_link = {
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
    links[link_key] = confirmed_link
    _persist_competitor_channel_link(confirmed_link)
    for candidate_id, candidate in list(candidates.items()):
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
        candidates[candidate_id] = candidate
        _persist_competitor_channel_candidate(candidate)
    _save_competitor_mapping_runs_only(db)
    return {"ok": True, "link": confirmed_link, "links": links}


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
            result = await _extract_competitor_content_with_retry(url, attempts=3 if source_id == "store77" else 2)
            specs = result.get("specs") if isinstance(result.get("specs"), dict) else {}
            return source_id, {
                "ok": True,
                "site": source_id,
                "url": url,
                "images": result.get("images") if isinstance(result.get("images"), list) else [],
                "specs": specs,
                "description": str(result.get("description") or "").strip(),
                "attempts": int(result.get("attempts") or 1),
            }
        except Exception as exc:
            return source_id, {
                "ok": False,
                "site": source_id,
                "url": url,
                "error": str(exc) or "EXTRACT_FAILED",
                "retryable": str(exc or "").upper() in {"TIMEOUT", "FETCH_ERROR", "EXTRACT_FAILED"},
            }

    extracted_pairs = await asyncio.gather(*[_one(link) for link in confirmed_links])
    extracted = {source_id: result for source_id, result in extracted_pairs if source_id}
    successful = {source_id: result for source_id, result in extracted.items() if result.get("ok")}
    errors = [
        {
            "source_id": source_id,
            "url": result.get("url"),
            "error": result.get("error") or "EXTRACT_FAILED",
            "retryable": bool(result.get("retryable", False)),
        }
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

    merged = await _merge_competitor_content_into_product(product, extracted=successful, links=link_by_source)
    saved = upsert_product_item(merged["product"])
    for source_id in successful.keys():
        link_key = f"{normalized_product_id}:{source_id}"
        link = link_by_source.get(source_id)
        if isinstance(link, dict):
            link["last_checked_at"] = now_iso()
            link["last_enriched_at"] = now_iso()
            _persist_competitor_channel_link(link)
    _save_competitor_mapping_runs_only(db)
    return {
        "ok": True,
        "product_id": normalized_product_id,
        "product": saved or merged["product"],
        "enriched_sources": merged["enriched_sources"],
        "matched_count": merged["matched_count"],
        "unmatched_count": merged["unmatched_count"],
        "errors": errors,
    }


@router.post("/discovery/products/{product_id}/ai-suggestions")
async def competitor_product_ai_suggestions(product_id: str) -> Dict[str, Any]:
    normalized_product_id = str(product_id or "").strip()
    if not normalized_product_id:
        raise HTTPException(status_code=400, detail="product_id required")

    products = query_products_full(ids=[normalized_product_id])
    product = products[0] if products else None
    if not isinstance(product, dict):
        raise HTTPException(status_code=404, detail="Product not found")

    result = await _competitor_ai_suggestion_items(product)
    items = result.get("items") if isinstance(result.get("items"), list) else []
    summary = {
        "total": len(items),
        "map_existing": sum(1 for item in items if item.get("action") == "map_existing"),
        "create_attribute": sum(1 for item in items if item.get("action") == "create_attribute"),
        "ignore": sum(1 for item in items if item.get("action") == "ignore"),
    }
    return {
        "ok": True,
        "product_id": normalized_product_id,
        "mode": result.get("mode") or "rules",
        "model": result.get("model"),
        "summary": summary,
        "items": items,
        "warnings": result.get("warnings") or [],
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
