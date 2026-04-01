from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse

from bs4 import BeautifulSoup

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

    return None


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
        images, specs, desc = extract_restore_product_content_from_html(html, base_url=url)
        dom_base = await fetch_restore_specs_dom(url)
        if dom_base:
            specs = {**specs, **dom_base}
        base = url.rstrip("/")
        spec_url = base if base.endswith("/spec") else f"{base}/spec/"
        extra: Dict[str, str] = {}
        spec_html = await fetch_html(spec_url)
        if spec_html and not spec_html.startswith("__ERROR__:") and not spec_html.startswith("__STATUS__:"):
            extra = extract_restore_specs_from_html(spec_html) or {}
            if extra:
                specs = {**specs, **extra}
        if not extra:
            dom_specs = await fetch_restore_specs_dom(spec_url)
            if dom_specs:
                specs = {**specs, **dom_specs}
        return {"site": site, "images": images, "specs": specs, "description": desc}

    if site == "store77":
        images, specs, desc = extract_store77_product_content_from_html(html, base_url=url)
        return {"site": site, "images": images, "specs": specs, "description": desc}

    return {"site": site, "images": [], "specs": {}, "description": ""}
