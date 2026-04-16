from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from app.core.json_store import read_doc
from app.storage.relational_pim_store import load_catalog_nodes, load_products_count
from app.storage.json_store import load_templates_db

router = APIRouter(prefix="/stats", tags=["stats"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data"

CATALOG_PATH = DATA_DIR / "catalog_nodes.json"
PRODUCTS_PATH = DATA_DIR / "products.json"
TEMPLATES_PATH = DATA_DIR / "templates.json"
COMPETITOR_MAPPING_PATH = DATA_DIR / "competitor_mapping.json"

_SUMMARY_CACHE_TTL_SECONDS = 300.0
_SUMMARY_CACHE_LOCK = threading.Lock()
_SUMMARY_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}
_SUMMARY_REFRESH_LOCK = threading.Lock()


def _read_json(path: Path, default: Any) -> Any:
    if path == CATALOG_PATH:
        return load_catalog_nodes()
    if path == TEMPLATES_PATH:
        return load_templates_db()
    return read_doc(path, default=default)


def _is_competitor_configured(row: Dict[str, Any]) -> bool:
    links = row.get("links") or {}
    has_link = bool((links.get("restore") or "").strip()) or bool((links.get("store77") or "").strip())
    mapping = row.get("mapping")
    has_map = bool(mapping) and isinstance(mapping, dict) and len(mapping) > 0
    return bool(has_link and has_map)


def _build_stats_summary() -> Dict[str, Any]:
    nodes = _read_json(CATALOG_PATH, default=[])
    templates_doc = _read_json(TEMPLATES_PATH, default={"templates": {}})
    competitors_doc = _read_json(COMPETITOR_MAPPING_PATH, default={"templates": {}})

    categories_count = len(nodes) if isinstance(nodes, list) else 0
    products_count = load_products_count()
    templates_count = len(templates_doc.get("templates") or {})

    comp_rows = competitors_doc.get("templates") or {}
    comp_total = len(comp_rows) if isinstance(comp_rows, dict) else 0
    comp_configured = 0
    if isinstance(comp_rows, dict):
        for row in comp_rows.values():
            if isinstance(row, dict) and _is_competitor_configured(row):
                comp_configured += 1

    return {
        "ok": True,
        "categories": int(categories_count),
        "products": int(products_count),
        "templates": int(templates_count),
        "connectors_configured": int(comp_configured),
        "connectors_total": int(comp_total),
    }


def _store_stats_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    with _SUMMARY_CACHE_LOCK:
        _SUMMARY_CACHE["payload"] = payload
        _SUMMARY_CACHE["expires_at"] = time.monotonic() + _SUMMARY_CACHE_TTL_SECONDS
    return payload


def warm_stats_summary() -> Dict[str, Any]:
    return _store_stats_summary(_build_stats_summary())


def _refresh_stats_summary_in_background() -> None:
    if not _SUMMARY_REFRESH_LOCK.acquire(blocking=False):
        return

    def _runner() -> None:
        try:
            warm_stats_summary()
        finally:
            _SUMMARY_REFRESH_LOCK.release()

    threading.Thread(target=_runner, name="stats-summary-refresh", daemon=True).start()


def get_stats_summary_cached() -> Dict[str, Any]:
    now = time.monotonic()
    with _SUMMARY_CACHE_LOCK:
        payload = _SUMMARY_CACHE.get("payload")
        expires_at = float(_SUMMARY_CACHE.get("expires_at") or 0.0)
    if payload and expires_at > now:
        return payload
    if payload:
        _refresh_stats_summary_in_background()
        return payload
    return warm_stats_summary()


@router.get("/summary")
def stats_summary() -> Dict[str, Any]:
    return get_stats_summary_cached()
