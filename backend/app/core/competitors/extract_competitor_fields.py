from __future__ import annotations

from typing import Any, Dict, List
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .biggeek import enrich_biggeek_content_for_variant
from .browser_fetch import fetch_html, fetch_restore_fields_meta, fetch_restore_specs_dom
from .restore_specs import (
    extract_restore_specs_from_html,
    extract_restore_spec_keys_from_html,
    extract_restore_spec_meta_from_html,
    build_restore_spec_meta,
    extract_restore_product_content_from_html,
)
from .store77 import extract_store77_fields, extract_store77_product_content_from_html


def detect_site_key(url: str) -> str | None:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return None
    if not host:
        return None

    if host.startswith("www."):
        host = host[4:]

    if host == "re-store.ru" or host.endswith(".re-store.ru"):
        return "restore"

    if host == "store77.net" or host.endswith(".store77.net"):
        return "store77"

    if host == "biggeek.ru" or host.endswith(".biggeek.ru"):
        return "biggeek"

    return None


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _flatten_image(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for key in ("url", "contentUrl"):
            if isinstance(value.get(key), str):
                return [value[key]]
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(_flatten_image(item))
        return out
    return []


def _json_ld_nodes(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    nodes: List[Dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text("", strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        stack = parsed if isinstance(parsed, list) else [parsed]
        while stack:
            node = stack.pop(0)
            if not isinstance(node, dict):
                continue
            nodes.append(node)
            graph = node.get("@graph")
            if isinstance(graph, list):
                stack.extend(item for item in graph if isinstance(item, dict))
    return nodes


def _generic_product_node(soup: BeautifulSoup) -> Dict[str, Any]:
    for node in _json_ld_nodes(soup):
        raw_type = node.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(str(item).lower() == "product" for item in types):
            return node
    return {}


def _extract_meta(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return _text(tag.get("content"))
    return ""


def _extract_generic_specs(soup: BeautifulSoup) -> Dict[str, str]:
    specs: Dict[str, str] = {}
    for row in soup.select("tr"):
        cells = [_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if len(cells) >= 2 and 1 <= len(cells[0]) <= 80 and cells[1]:
            specs.setdefault(cells[0], cells[1])
    for item in soup.select("dl"):
        terms = item.find_all("dt")
        values = item.find_all("dd")
        for term, value in zip(terms, values):
            key = _text(term.get_text(" ", strip=True))
            val = _text(value.get_text(" ", strip=True))
            if key and val and len(key) <= 80:
                specs.setdefault(key, val)
    return specs


def _extract_generic_content_from_html(html: str, base_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html or "", "html.parser")
    product = _generic_product_node(soup)
    images = _flatten_image(product.get("image") if product else None)
    og_image = _extract_meta(soup, "og:image")
    if og_image:
        images.append(og_image)
    normalized_images: List[str] = []
    for image in images:
        normalized = urljoin(base_url, str(image or "").strip())
        if normalized and normalized not in normalized_images:
            normalized_images.append(normalized)
    desc = _text(product.get("description") if product else "") or _extract_meta(soup, "description", "og:description")
    return {
        "images": normalized_images[:50],
        "specs": _extract_generic_specs(soup),
        "description": desc,
    }


async def extract_competitor_fields(url: str, return_meta: bool = False) -> Any:
    site = detect_site_key(url)
    if not site:
        raise RuntimeError("UNSUPPORTED_SITE")

    html = await fetch_html(url)
    if not html:
        raise RuntimeError("EMPTY_HTML")

    if html.startswith("__ERROR__:"):
        head = html.split("\n", 1)[0]
        code = head.replace("__ERROR__:", "").replace("__", "")
        raise RuntimeError(code or "FETCH_ERROR")

    if html.startswith("__STATUS__:"):
        head = html.split("\n", 1)[0]
        code = head.replace("__STATUS__:", "").replace("__", "")
        raise RuntimeError(f"HTTP_{code}")

    if site == "restore":
        items = await fetch_restore_fields_meta(url)
        meta = build_restore_spec_meta([(i.get("name"), i.get("section")) for i in items]) if items else []
        fields = [m.get("name") for m in meta if m.get("name")] if meta else []

        if not fields:
            meta = extract_restore_spec_meta_from_html(html)
            fields = [m.get("name") for m in meta if m.get("name")] if meta else []
        if not fields:
            fields = extract_restore_spec_keys_from_html(html)
        if not fields:
            specs = extract_restore_specs_from_html(html)
            fields = list(specs.keys()) if isinstance(specs, dict) else (specs or [])
        if not fields:
            raise RuntimeError("NO_FIELDS_RESTORE")

        if return_meta:
            return {"fields": fields, "fields_meta": meta}
        return fields

    if site == "store77":
        soup = BeautifulSoup(html, "html.parser")
        fields = extract_store77_fields(soup)
        if not fields:
            raise RuntimeError("NO_FIELDS_STORE77")
        return {"fields": fields, "fields_meta": []} if return_meta else fields

    return []


async def extract_competitor_content(url: str) -> Dict[str, Any]:
    site = detect_site_key(url)
    if not site:
        raise RuntimeError("UNSUPPORTED_SITE")

    html = await fetch_html(url, timeout_ms=30000 if site == "restore" else 45000)
    if not html:
        raise RuntimeError("EMPTY_HTML")

    if html.startswith("__ERROR__:"):
        head = html.split("\n", 1)[0]
        code = head.replace("__ERROR__:", "").replace("__", "")
        raise RuntimeError(code or "FETCH_ERROR")

    if html.startswith("__STATUS__:"):
        head = html.split("\n", 1)[0]
        code = head.replace("__STATUS__:", "").replace("__", "")
        raise RuntimeError(f"HTTP_{code}")

    if site == "restore":
        images, specs, desc = extract_restore_product_content_from_html(html, base_url=url)
        # Product pages usually contain enough rendered specs after fetch_html's
        # re-store wait. Only use extra browser passes when the first pass is
        # clearly incomplete, otherwise a single competitor can exhaust the
        # whole enrichment job timeout.
        if len(specs) < 25:
            dom_base = await fetch_restore_specs_dom(url, timeout_ms=25000)
            if dom_base:
                specs = {**specs, **dom_base}
        if len(specs) < 25:
            base = url.rstrip("/")
            spec_url = base if base.endswith("/spec") else f"{base}/spec/"
            extra: Dict[str, str] = {}
            spec_html = await fetch_html(spec_url, timeout_ms=25000)
            if spec_html and not spec_html.startswith("__ERROR__:") and not spec_html.startswith("__STATUS__:"):
                extra = extract_restore_specs_from_html(spec_html) or {}
                if extra:
                    specs = {**specs, **extra}
            if not extra:
                dom_specs = await fetch_restore_specs_dom(spec_url, timeout_ms=25000)
                if dom_specs:
                    specs = {**specs, **dom_specs}
        return {"site": site, "images": images, "specs": specs, "description": desc}

    if site == "store77":
        images, specs, desc = extract_store77_product_content_from_html(html, base_url=url)
        return {"site": site, "images": images, "specs": specs, "description": desc}

    if site == "biggeek":
        content = _extract_generic_content_from_html(html, url)
        content = enrich_biggeek_content_for_variant(url, content, BeautifulSoup(html, "html.parser"))
        return {"site": site, **content}

    return {"site": site, "images": [], "specs": {}, "description": ""}
