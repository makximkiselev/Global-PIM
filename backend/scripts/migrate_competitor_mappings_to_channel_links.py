#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Dict

from app.api.routes.competitor_mapping import _ensure_row_shape, _persist_competitor_mapping_row
from app.storage.json_store import load_competitor_mapping_db


def _rows(db: Dict[str, Any], key: str) -> Dict[str, Dict[str, Any]]:
    raw = db.get(key) if isinstance(db.get(key), dict) else {}
    return {str(row_id): value for row_id, value in raw.items() if isinstance(value, dict)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill legacy competitor category/template mappings from JSON document into pim_channel_links."
    )
    parser.add_argument("--apply", action="store_true", help="Write rows. Without this flag the script only reports counts.")
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

    mode = "applied" if args.apply else "dry-run"
    print(f"{mode}: categories={category_count}, templates={template_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
