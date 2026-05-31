from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import urlparse


def canonical_media_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return raw
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host == "ir.ozone.ru" or host.endswith(".ozone.ru"):
        return f"ozone:{path.lower()}"
    return f"{host}{path}".lower()


def media_identity_keys(item: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    for field in ("external_url", "source_image_url", "url"):
        value = str(item.get(field) or "").strip()
        if value:
            keys.add(value)
            canonical = canonical_media_url(value)
            if canonical:
                keys.add(canonical)
    source_url = str(item.get("source_url") or "").strip()
    source_host = str(item.get("source_host") or "").strip()
    source_type = str(item.get("source_type") or "").strip()
    if source_url and (source_type == "external_import" or source_host or Path(urlparse(source_url).path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}):
        keys.add(source_url)
        canonical = canonical_media_url(source_url)
        if canonical:
            keys.add(canonical)
    return keys


def dedupe_media_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        keys = media_identity_keys(item)
        if keys and seen.intersection(keys):
            continue
        out.append(item)
        seen.update(keys)
    return out
