from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from app.core.json_store import read_doc

router = APIRouter(prefix="/stats", tags=["stats"])

BASE_DIR = Path(__file__).resolve().parents[3]  # backend/
DATA_DIR = BASE_DIR / "data"

CATALOG_PATH = DATA_DIR / "catalog_nodes.json"
PRODUCTS_PATH = DATA_DIR / "products.json"
TEMPLATES_PATH = DATA_DIR / "templates.json"
COMPETITOR_MAPPING_PATH = DATA_DIR / "competitor_mapping.json"


def _read_json(path: Path, default: Any) -> Any:
    return read_doc(path, default=default)


def _is_competitor_configured(row: Dict[str, Any]) -> bool:
    links = row.get("links") or {}
    has_link = bool((links.get("restore") or "").strip()) or bool((links.get("store77") or "").strip())
    mapping = row.get("mapping")
    has_map = bool(mapping) and isinstance(mapping, dict) and len(mapping) > 0
    return bool(has_link and has_map)


@router.get("/summary")
def stats_summary() -> Dict[str, Any]:
    nodes = _read_json(CATALOG_PATH, default=[])
    products_doc = _read_json(PRODUCTS_PATH, default={"items": []})
    templates_doc = _read_json(TEMPLATES_PATH, default={"templates": {}})
    competitors_doc = _read_json(COMPETITOR_MAPPING_PATH, default={"templates": {}})

    categories_count = len(nodes) if isinstance(nodes, list) else 0
    products_count = len(products_doc.get("items") or [])
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
