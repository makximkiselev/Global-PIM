from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.json_store import read_doc, with_lock, write_doc
from app.core.tenant_context import current_tenant_organization_id
from app.core.products.service import patch_product_service
from app.storage.relational_pim_store import query_products_full

router = APIRouter(prefix="/competitor-catalog", tags=["competitor-catalog"])

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data"
MAX_PAGES_HARD_LIMIT = 80
MAX_PRODUCTS_HARD_LIMIT = 120
REQUEST_TIMEOUT_SECONDS = 12.0
USER_AGENT = "SmartPim competitor catalog importer (+https://pim.id-smart.ru)"


class CompetitorCatalogRunRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    start_url: str = Field(min_length=8, max_length=2048)
    max_pages: int = Field(default=35, ge=1, le=MAX_PAGES_HARD_LIMIT)
    max_products: int = Field(default=60, ge=1, le=MAX_PRODUCTS_HARD_LIMIT)


class CompetitorCatalogLinkRequest(BaseModel):
    product_id: str = Field(min_length=3, max_length=120)
    pim_product_id: str = Field(default="", max_length=120)
    status: str = Field(default="linked", max_length=24)


class CompetitorCatalogApplyRequest(BaseModel):
    apply_media: bool = True
    apply_description: bool = True
    apply_specs: bool = True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tenant_safe_key() -> str:
    raw = str(current_tenant_organization_id() or "org_default").strip() or "org_default"
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw).strip("_") or "org_default"


def _store_path() -> Path:
    return DATA_DIR / f"competitor_catalog_imports_{_tenant_safe_key()}.json"


def _default_store() -> dict[str, Any]:
    return {"version": 1, "runs": {}, "products": {}, "links": {}}


def _load_store() -> dict[str, Any]:
    doc = read_doc(_store_path(), default=_default_store())
    if not isinstance(doc, dict):
        doc = _default_store()
    if not isinstance(doc.get("runs"), dict):
        doc["runs"] = {}
    if not isinstance(doc.get("products"), dict):
        doc["products"] = {}
    if not isinstance(doc.get("links"), dict):
        doc["links"] = {}
    doc["version"] = 1
    return doc


def _save_store(doc: dict[str, Any]) -> None:
    write_doc(_store_path(), doc)


def _normalize_url(url: str, base_url: str = "") -> str:
    value = str(url or "").strip()
    if base_url:
        value = urljoin(base_url, value)
    value, _fragment = urldefrag(value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path or "/"
    normalized = parsed._replace(path=path, fragment="")
    return normalized.geturl().rstrip("/")


def _same_host(url: str, host: str) -> bool:
    return (urlparse(url).hostname or "").lower() == host.lower()


def _run_id_for(start_url: str) -> str:
    return f"cci_{hashlib.sha1(f'{_tenant_safe_key()}:{start_url}:{_now_iso()}'.encode('utf-8')).hexdigest()[:16]}"


def _product_id_for(url: str) -> str:
    return f"cp_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}"


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm_for_match(value: Any) -> str:
    raw = _text(value).lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9]+", " ", raw).strip()


def _tokens_for_match(value: Any) -> set[str]:
    ignored = {"смартфон", "телефон", "apple", "samsung", "xiaomi", "global", "original", "new", "для", "and", "the"}
    return {token for token in _norm_for_match(value).split() if len(token) >= 2 and token not in ignored}


def _candidate_score(competitor_product: dict[str, Any], pim_product: dict[str, Any]) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0
    c_title = _norm_for_match(competitor_product.get("title"))
    p_title = _norm_for_match(pim_product.get("title"))
    c_sku = _norm_for_match(competitor_product.get("sku"))
    p_sku_gt = _norm_for_match(pim_product.get("sku_gt"))
    p_sku_pim = _norm_for_match(pim_product.get("sku_pim"))
    if c_sku and c_sku in {p_sku_gt, p_sku_pim}:
        score += 95
        reasons.append("SKU совпал")
    c_brand = _norm_for_match(competitor_product.get("brand"))
    if c_brand and c_brand in p_title:
        score += 10
        reasons.append("бренд найден в PIM-названии")
    if p_title and c_title and (p_title in c_title or c_title in p_title):
        score += 55
        reasons.append("название входит целиком")
    c_tokens = _tokens_for_match(c_title)
    p_tokens = _tokens_for_match(p_title)
    overlap = c_tokens.intersection(p_tokens)
    if c_tokens and p_tokens:
        ratio = len(overlap) / max(len(c_tokens), 1)
        score += int(ratio * 70)
        if overlap:
            reasons.append(f"общие токены: {', '.join(sorted(overlap)[:5])}")
    for token in ("128", "256", "512", "1tb", "1тб", "black", "white", "pink", "blue", "titanium", "desert", "natural"):
        if token in c_tokens and token in p_tokens:
            score += 6
    return min(score, 100), reasons


def _link_payload(store: dict[str, Any], competitor_product_id: str) -> dict[str, Any] | None:
    link = store.get("links", {}).get(competitor_product_id)
    return link if isinstance(link, dict) else None


def _public_product(product: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    out = dict(product)
    out["link"] = _link_payload(store, str(product.get("id") or "")) or None
    return out


def _suggest_candidates(competitor_product: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    products = query_products_full(limit=900)
    candidates: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        score, reasons = _candidate_score(competitor_product, product)
        if score < 18:
            continue
        candidates.append(
            {
                "product_id": product.get("id"),
                "title": product.get("title"),
                "sku_gt": product.get("sku_gt"),
                "sku_pim": product.get("sku_pim"),
                "category_id": product.get("category_id"),
                "group_id": product.get("group_id"),
                "score": score,
                "reasons": reasons,
            }
        )
    candidates.sort(key=lambda row: (int(row.get("score") or 0), str(row.get("title") or "")), reverse=True)
    return candidates[:limit]


def _feature_code_for_spec(name: str) -> str:
    base = _norm_for_match(name).replace(" ", "_")
    safe = re.sub(r"[^a-zа-я0-9_]+", "_", base).strip("_")
    return safe[:80] or f"competitor_spec_{hashlib.sha1(name.encode('utf-8')).hexdigest()[:8]}"


def _media_key(item: dict[str, Any]) -> str:
    return str(item.get("external_url") or item.get("source_image_url") or item.get("url") or "").strip()


def _build_competitor_apply_plan(competitor_product: dict[str, Any], pim_product: dict[str, Any]) -> dict[str, Any]:
    content = pim_product.get("content") if isinstance(pim_product.get("content"), dict) else {}
    existing_media = content.get("media_images") if isinstance(content.get("media_images"), list) else []
    existing_media_keys = {_media_key(item) for item in existing_media if isinstance(item, dict)}
    media_to_add = []
    for index, url in enumerate(competitor_product.get("images") if isinstance(competitor_product.get("images"), list) else []):
        image_url = str(url or "").strip()
        if not image_url or image_url in existing_media_keys:
            continue
        media_to_add.append(
            {
                "url": image_url,
                "external_url": image_url,
                "source_image_url": image_url,
                "source_type": "competitor_catalog",
                "source_product_id": competitor_product.get("id"),
                "source_url": competitor_product.get("url"),
                "caption": competitor_product.get("title") or "",
                "selected": True,
                "export_order": len(existing_media) + len(media_to_add) + 1,
            }
        )

    existing_description = _text(content.get("description"))
    competitor_description = _text(competitor_product.get("description"))
    description_to_apply = competitor_description if competitor_description and not existing_description else ""

    existing_features = content.get("features") if isinstance(content.get("features"), list) else []
    feature_by_key: dict[str, dict[str, Any]] = {}
    for feature in existing_features:
        if not isinstance(feature, dict):
            continue
        for key in (feature.get("code"), feature.get("name")):
            normalized = _norm_for_match(key)
            if normalized:
                feature_by_key[normalized] = feature

    specs = competitor_product.get("specs") if isinstance(competitor_product.get("specs"), dict) else {}
    specs_to_fill: list[dict[str, Any]] = []
    specs_to_create: list[dict[str, Any]] = []
    for raw_name, raw_value in specs.items():
        name = _text(raw_name)
        value = _text(raw_value)
        if not name or not value:
            continue
        existing = feature_by_key.get(_norm_for_match(name))
        proposal = {
            "name": name,
            "code": _feature_code_for_spec(name),
            "value": value,
            "source": "competitor_catalog",
            "source_product_id": competitor_product.get("id"),
            "source_url": competitor_product.get("url"),
        }
        if existing:
            if not _text(existing.get("value")):
                proposal["code"] = _text(existing.get("code")) or proposal["code"]
                proposal["existing_name"] = _text(existing.get("name")) or name
                specs_to_fill.append(proposal)
        else:
            specs_to_create.append(proposal)

    return {
        "media_to_add": media_to_add,
        "description_to_apply": description_to_apply,
        "description_skipped_reason": "target_not_empty" if competitor_description and existing_description else "",
        "specs_to_fill": specs_to_fill,
        "specs_to_create": specs_to_create[:80],
        "summary": {
            "media_to_add": len(media_to_add),
            "description_ready": bool(description_to_apply),
            "specs_to_fill": len(specs_to_fill),
            "specs_to_create": min(len(specs_to_create), 80),
        },
    }


def _apply_competitor_plan(pim_product: dict[str, Any], competitor_product: dict[str, Any], plan: dict[str, Any], req: CompetitorCatalogApplyRequest) -> dict[str, Any]:
    content = pim_product.get("content") if isinstance(pim_product.get("content"), dict) else {}
    next_content = dict(content)
    applied = {"media": 0, "description": False, "specs": 0}

    if req.apply_media:
        media_images = list(next_content.get("media_images") if isinstance(next_content.get("media_images"), list) else [])
        additions = [item for item in plan.get("media_to_add", []) if isinstance(item, dict)]
        if additions:
            media_images.extend(additions)
            next_content["media_images"] = media_images
            next_content["media"] = media_images
            applied["media"] = len(additions)

    if req.apply_description and plan.get("description_to_apply"):
        next_content["description"] = plan.get("description_to_apply")
        applied["description"] = True

    if req.apply_specs:
        features = list(next_content.get("features") if isinstance(next_content.get("features"), list) else [])
        by_key: dict[str, int] = {}
        for idx, feature in enumerate(features):
            if not isinstance(feature, dict):
                continue
            for key in (feature.get("code"), feature.get("name")):
                normalized = _norm_for_match(key)
                if normalized:
                    by_key[normalized] = idx
        for proposal in list(plan.get("specs_to_fill") or []) + list(plan.get("specs_to_create") or []):
            if not isinstance(proposal, dict):
                continue
            code = _text(proposal.get("code"))
            name = _text(proposal.get("name"))
            value = _text(proposal.get("value"))
            if not name or not value:
                continue
            idx = by_key.get(_norm_for_match(code)) if code else None
            if idx is None:
                idx = by_key.get(_norm_for_match(name))
            if idx is not None and 0 <= idx < len(features) and isinstance(features[idx], dict):
                if _text(features[idx].get("value")):
                    continue
                source_values = features[idx].get("source_values") if isinstance(features[idx].get("source_values"), dict) else {}
                features[idx] = {
                    **features[idx],
                    "value": value,
                    "source_values": {
                        **source_values,
                        "competitor_catalog": {
                            "value": value,
                            "source_product_id": competitor_product.get("id"),
                            "source_url": competitor_product.get("url"),
                        },
                    },
                }
            else:
                features.append(
                    {
                        "code": code or _feature_code_for_spec(name),
                        "name": name,
                        "value": value,
                        "type": "text",
                        "required": False,
                        "scope": "competitor",
                        "field_layer": "features",
                        "fill_source": "competitor_catalog",
                        "locked": False,
                        "source_values": {
                            "competitor_catalog": {
                                "value": value,
                                "source_product_id": competitor_product.get("id"),
                                "source_url": competitor_product.get("url"),
                            }
                        },
                    }
                )
                by_key[_norm_for_match(code or name)] = len(features) - 1
            applied["specs"] += 1
        next_content["features"] = features

    result = patch_product_service(str(pim_product.get("id") or ""), {"content": next_content})
    return {"product": result.get("product"), "applied": applied}


def _jsonld_nodes(soup: BeautifulSoup) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop(0)
            if isinstance(node, dict):
                out.append(node)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    stack.extend(graph)
            elif isinstance(node, list):
                stack.extend(node)
    return out


def _node_type(node: dict[str, Any]) -> str:
    value = node.get("@type")
    if isinstance(value, list):
        value = " ".join(str(x) for x in value)
    return str(value or "").lower()


def _extract_meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        found = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        content = _text(found.get("content") if found else "")
        if content:
            return content
    return ""


def _first_jsonld_product(soup: BeautifulSoup) -> dict[str, Any]:
    for node in _jsonld_nodes(soup):
        if "product" in _node_type(node):
            return node
    return {}


def _flatten_image(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    out: list[str] = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("url") or item.get("contentUrl")
        url = str(item or "").strip()
        if url and url not in out:
            out.append(url)
    return out


def _extract_price(product_node: dict[str, Any], soup: BeautifulSoup) -> dict[str, Any]:
    offers = product_node.get("offers") if isinstance(product_node, dict) else {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        offers = {}
    price = _text(offers.get("price") or _extract_meta(soup, "product:price:amount", "og:price:amount"))
    currency = _text(offers.get("priceCurrency") or _extract_meta(soup, "product:price:currency", "og:price:currency"))
    return {"price": price, "currency": currency}


def _extract_specs(soup: BeautifulSoup) -> dict[str, str]:
    specs: dict[str, str] = {}
    for row in soup.select("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) < 2:
            continue
        key = _text(cells[0].get_text(" ", strip=True))
        value = _text(cells[1].get_text(" ", strip=True))
        if key and value and len(key) <= 96:
            specs.setdefault(key, value)
    for row in soup.select("dl"):
        terms = row.find_all("dt")
        definitions = row.find_all("dd")
        for term, definition in zip(terms, definitions):
            key = _text(term.get_text(" ", strip=True))
            value = _text(definition.get_text(" ", strip=True))
            if key and value and len(key) <= 96:
                specs.setdefault(key, value)
    return dict(list(specs.items())[:80])


def _extract_product(page_url: str, html: str) -> dict[str, Any] | None:
    soup = BeautifulSoup(html, "html.parser")
    product_node = _first_jsonld_product(soup)
    h1 = soup.find("h1")
    title = _text(product_node.get("name") if product_node else "") or _text(h1.get_text(" ", strip=True) if h1 else "")
    title = title or _extract_meta(soup, "og:title") or _text(soup.title.get_text(" ", strip=True) if soup.title else "")
    if not title:
        return None

    specs = _extract_specs(soup)
    images = _flatten_image(product_node.get("image") if product_node else None)
    og_image = _extract_meta(soup, "og:image")
    if og_image and og_image not in images:
        images.append(og_image)
    images = [_normalize_url(img, page_url) for img in images]
    images = [img for img in images if img][:16]
    price = _extract_price(product_node, soup)
    description = _text(product_node.get("description") if product_node else "") or _extract_meta(soup, "description", "og:description")
    brand = product_node.get("brand") if isinstance(product_node, dict) else ""
    if isinstance(brand, dict):
        brand = brand.get("name")
    sku = _text(product_node.get("sku") if product_node else "")

    signals = 0
    if product_node:
        signals += 3
    if images:
        signals += 1
    if price.get("price"):
        signals += 1
    if specs:
        signals += 1
    if h1:
        signals += 1
    if signals < 3:
        return None

    return {
        "id": _product_id_for(page_url),
        "url": page_url,
        "title": title[:300],
        "description": description[:1000],
        "brand": _text(brand),
        "sku": sku,
        "price": price.get("price", ""),
        "currency": price.get("currency", ""),
        "images": images,
        "specs": specs,
        "spec_count": len(specs),
        "source_type": "competitor_site",
        "confidence": min(100, signals * 16),
        "updated_at": _now_iso(),
    }


def _score_product_link(url: str) -> int:
    path = urlparse(url).path.lower()
    score = 0
    for token in ("product", "products", "catalog", "item", "sku", "p/", "iphone", "samsung", "smartfon", "noutbuk", "planshet"):
        if token in path:
            score += 1
    if re.search(r"[-_/](\d{4,}|[a-z0-9]{8,})(?:/|$)", path):
        score += 1
    if path.count("/") >= 2:
        score += 1
    return score


def _extract_links(page_url: str, html: str, host: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    for anchor in soup.find_all("a", href=True):
        url = _normalize_url(anchor.get("href"), page_url)
        if not url or not _same_host(url, host):
            continue
        path = urlparse(url).path.lower()
        if any(skip in path for skip in ("/cart", "/basket", "/login", "/auth", "/compare", "/wishlist", "/search")):
            continue
        if url not in out:
            out.append(url)
    return out


def _robots_allows(robots_text: str) -> bool:
    current_applies = False
    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key = key.lower()
        if key == "user-agent":
            current_applies = value in {"*", USER_AGENT}
        elif current_applies and key == "disallow" and value.strip() == "/":
            return False
    return True


async def _fetch(client: httpx.AsyncClient, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    content_type = str(response.headers.get("content-type") or "").lower()
    if "text/html" not in content_type and "xml" not in content_type and "text/plain" not in content_type and content_type:
        return ""
    return response.text


async def _sitemap_urls(client: httpx.AsyncClient, start_url: str, host: str, limit: int) -> list[str]:
    sitemap_url = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}/sitemap.xml"
    try:
        xml = await _fetch(client, sitemap_url)
    except Exception:
        return []
    urls = re.findall(r"<loc>\s*([^<]+)\s*</loc>", xml, flags=re.I)
    out: list[str] = []
    for url in urls:
        normalized = _normalize_url(url)
        if normalized and _same_host(normalized, host) and normalized not in out:
            out.append(normalized)
        if len(out) >= limit:
            break
    return out


async def _crawl_site(request: CompetitorCatalogRunRequest) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start_url = _normalize_url(request.start_url)
    if not start_url:
        raise HTTPException(status_code=400, detail="BAD_START_URL")
    parsed = urlparse(start_url)
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=400, detail="BAD_START_URL")

    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=5.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.7"}
    pages_seen: set[str] = set()
    queued: list[str] = [start_url]
    products: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
        try:
            robots = await _fetch(client, f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            if robots and not _robots_allows(robots):
                raise HTTPException(status_code=400, detail="ROBOTS_DISALLOW_ALL")
        except HTTPException:
            raise
        except Exception:
            pass

        sitemap_candidates = await _sitemap_urls(client, start_url, host, request.max_pages)
        queued.extend([url for url in sitemap_candidates if url not in queued])

        while queued and len(pages_seen) < request.max_pages and len(products) < request.max_products:
            url = queued.pop(0)
            if url in pages_seen or not _same_host(url, host):
                continue
            pages_seen.add(url)
            try:
                html = await _fetch(client, url)
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}")
                await asyncio.sleep(0.08)
                continue
            if not html:
                continue
            product = _extract_product(url, html)
            if product:
                products[product["id"]] = product
            links = _extract_links(url, html, host)
            links.sort(key=_score_product_link, reverse=True)
            for link in links:
                if link not in pages_seen and link not in queued:
                    queued.append(link)
            await asyncio.sleep(0.08)

    run = {
        "id": _run_id_for(start_url),
        "name": request.name.strip() or host,
        "start_url": start_url,
        "host": host,
        "status": "completed",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "pages_scanned": len(pages_seen),
        "products_found": len(products),
        "errors": errors[:20],
        "product_ids": list(products.keys()),
        "limits": {"max_pages": request.max_pages, "max_products": request.max_products},
    }
    return run, list(products.values())


@router.get("/runs")
def list_competitor_catalog_runs() -> dict[str, Any]:
    store = _load_store()
    runs = list(store.get("runs", {}).values())
    runs.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return {
        "runs": runs[:30],
        "total_products": len(store.get("products", {})),
        "updated_at": max((str(row.get("updated_at") or "") for row in runs), default=None),
    }


@router.get("/runs/{run_id}")
def get_competitor_catalog_run(run_id: str) -> dict[str, Any]:
    store = _load_store()
    run = store.get("runs", {}).get(run_id)
    if not isinstance(run, dict):
        raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")
    products = [store.get("products", {}).get(pid) for pid in run.get("product_ids", [])]
    return {"run": run, "products": [_public_product(p, store) for p in products if isinstance(p, dict)]}


@router.get("/products/{product_id}/suggestions")
def get_competitor_product_suggestions(product_id: str) -> dict[str, Any]:
    store = _load_store()
    product = store.get("products", {}).get(product_id)
    if not isinstance(product, dict):
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    return {
        "product": _public_product(product, store),
        "candidates": _suggest_candidates(product),
    }


@router.post("/products/{product_id}/link")
def save_competitor_product_link(product_id: str, payload: CompetitorCatalogLinkRequest) -> dict[str, Any]:
    if payload.product_id != product_id:
        raise HTTPException(status_code=400, detail="PRODUCT_ID_MISMATCH")
    status = payload.status.strip().lower()
    if status not in {"linked", "ignored", "unlinked"}:
        raise HTTPException(status_code=400, detail="BAD_LINK_STATUS")

    lock = with_lock(f"competitor_catalog_imports:{_tenant_safe_key()}")
    if not lock.acquire(timeout=10):
        raise HTTPException(status_code=423, detail="STORE_LOCKED")
    try:
        store = _load_store()
        product = store.get("products", {}).get(product_id)
        if not isinstance(product, dict):
            raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
        if status == "unlinked":
            store["links"].pop(product_id, None)
        elif status == "ignored":
            store["links"][product_id] = {
                "status": "ignored",
                "pim_product_id": "",
                "updated_at": _now_iso(),
            }
        else:
            pim_product_id = payload.pim_product_id.strip()
            if not pim_product_id:
                raise HTTPException(status_code=400, detail="PIM_PRODUCT_REQUIRED")
            found = query_products_full(ids=[pim_product_id], limit=1)
            if not found:
                raise HTTPException(status_code=404, detail="PIM_PRODUCT_NOT_FOUND")
            store["links"][product_id] = {
                "status": "linked",
                "pim_product_id": pim_product_id,
                "pim_title": found[0].get("title"),
                "sku_gt": found[0].get("sku_gt"),
                "sku_pim": found[0].get("sku_pim"),
                "updated_at": _now_iso(),
            }
        _save_store(store)
        return {"product": _public_product(store["products"][product_id], store)}
    finally:
        lock.release()


@router.get("/products/{product_id}/apply-preview")
def preview_competitor_product_apply(product_id: str) -> dict[str, Any]:
    store = _load_store()
    competitor_product = store.get("products", {}).get(product_id)
    if not isinstance(competitor_product, dict):
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    link = _link_payload(store, product_id)
    if not link or link.get("status") != "linked":
        raise HTTPException(status_code=400, detail="COMPETITOR_PRODUCT_NOT_LINKED")
    pim_product_id = str(link.get("pim_product_id") or "").strip()
    pim_products = query_products_full(ids=[pim_product_id], limit=1)
    if not pim_products:
        raise HTTPException(status_code=404, detail="PIM_PRODUCT_NOT_FOUND")
    plan = _build_competitor_apply_plan(competitor_product, pim_products[0])
    return {
        "competitor_product": _public_product(competitor_product, store),
        "pim_product": {
            "id": pim_products[0].get("id"),
            "title": pim_products[0].get("title"),
            "sku_gt": pim_products[0].get("sku_gt"),
            "sku_pim": pim_products[0].get("sku_pim"),
            "category_id": pim_products[0].get("category_id"),
        },
        "plan": plan,
    }


@router.post("/products/{product_id}/apply")
def apply_competitor_product_to_pim(product_id: str, payload: CompetitorCatalogApplyRequest) -> dict[str, Any]:
    store = _load_store()
    competitor_product = store.get("products", {}).get(product_id)
    if not isinstance(competitor_product, dict):
        raise HTTPException(status_code=404, detail="PRODUCT_NOT_FOUND")
    link = _link_payload(store, product_id)
    if not link or link.get("status") != "linked":
        raise HTTPException(status_code=400, detail="COMPETITOR_PRODUCT_NOT_LINKED")
    pim_product_id = str(link.get("pim_product_id") or "").strip()
    pim_products = query_products_full(ids=[pim_product_id], limit=1)
    if not pim_products:
        raise HTTPException(status_code=404, detail="PIM_PRODUCT_NOT_FOUND")
    plan = _build_competitor_apply_plan(competitor_product, pim_products[0])
    result = _apply_competitor_plan(pim_products[0], competitor_product, plan, payload)
    updated_product = result.get("product") if isinstance(result.get("product"), dict) else pim_products[0]
    next_plan = _build_competitor_apply_plan(competitor_product, updated_product)
    link["last_applied_at"] = _now_iso()
    link["last_applied"] = result.get("applied")
    store.setdefault("links", {})[product_id] = link
    _save_store(store)
    return {
        "competitor_product": _public_product(competitor_product, store),
        "pim_product": result.get("product"),
        "applied": result.get("applied"),
        "plan": next_plan,
    }


@router.post("/runs")
async def create_competitor_catalog_run(payload: CompetitorCatalogRunRequest) -> dict[str, Any]:
    run, products = await _crawl_site(payload)
    lock = with_lock(f"competitor_catalog_imports:{_tenant_safe_key()}")
    if not lock.acquire(timeout=10):
        raise HTTPException(status_code=423, detail="STORE_LOCKED")
    try:
        store = _load_store()
        store["runs"][run["id"]] = run
        for product in products:
            store["products"][product["id"]] = product
        _save_store(store)
    finally:
        lock.release()
    store = _load_store()
    return {"run": run, "products": [_public_product(product, store) for product in products]}
