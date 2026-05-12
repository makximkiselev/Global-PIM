#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Dict

from app.api.routes.competitor_mapping import _ensure_row_shape, _persist_competitor_mapping_row
from app.storage.json_store import (
    COMPETITOR_MAPPING_FILE,
    DEFAULT_COMPETITOR_MAPPING,
    _read_json,
    _write_json_atomic,
    load_competitor_mapping_db,
    save_competitor_mapping_db,
)


def _clear_legacy_root_mappings() -> None:
    db = _read_json(COMPETITOR_MAPPING_FILE, DEFAULT_COMPETITOR_MAPPING)
    if not isinstance(db, dict):
        return
    changed = bool((db.get("categories") or {}) or (db.get("templates") or {}))
    if not changed:
        return
    db["categories"] = {}
    db["templates"] = {}
    _write_json_atomic(COMPETITOR_MAPPING_FILE, db)


def _rows(db: Dict[str, Any], key: str) -> Dict[str, Dict[str, Any]]:
    raw = db.get(key) if isinstance(db.get(key), dict) else {}
    return {str(row_id): value for row_id, value in raw.items() if isinstance(value, dict)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill legacy competitor category/template mappings from JSON document into pim_channel_links."
    )
    parser.add_argument("--apply", action="store_true", help="Write rows. Without this flag the script only reports counts.")
    parser.add_argument(
        "--clear-json",
        action="store_true",
        help="After --apply, remove legacy categories/templates from the JSON document.",
    )
    args = parser.parse_args()

    db = load_competitor_mapping_db()
    categories = _rows(db, "categories")
    templates = _rows(db, "templates")

    category_count = 0
    template_count = 0
    for category_id, row in categories.items():
        shaped = _ensure_row_shape(row)
        category_count += 1
        if args.apply:
            _persist_competitor_mapping_row("category", category_id, shaped)

    for template_id, row in templates.items():
        shaped = _ensure_row_shape(row)
        template_count += 1
        if args.apply:
            _persist_competitor_mapping_row("template", template_id, shaped)

    if args.apply and args.clear_json:
        if categories or templates:
            db["categories"] = {}
            db["templates"] = {}
            save_competitor_mapping_db(db)
        _clear_legacy_root_mappings()

    mode = "applied" if args.apply else "dry-run"
    cleared_categories = category_count if args.apply and args.clear_json else 0
    cleared_templates = template_count if args.apply and args.clear_json else 0
    print(
        f"{mode}: categories={category_count}, templates={template_count}, "
        f"json_categories_cleared={cleared_categories}, json_templates_cleared={cleared_templates}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
