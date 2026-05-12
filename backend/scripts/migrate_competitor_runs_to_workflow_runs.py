#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Dict

from app.api.routes.competitor_mapping import _ensure_discovery_doc, _persist_discovery_run
from app.storage.json_store import (
    COMPETITOR_MAPPING_FILE,
    DEFAULT_COMPETITOR_MAPPING,
    _read_json,
    _write_json_atomic,
    load_competitor_mapping_db,
    save_competitor_mapping_db,
)


def _clear_legacy_root_runs() -> None:
    db = _read_json(COMPETITOR_MAPPING_FILE, DEFAULT_COMPETITOR_MAPPING)
    if not isinstance(db, dict):
        return
    discovery = _ensure_discovery_doc(db)
    if not (discovery.get("runs") or {}):
        return
    discovery["runs"] = {}
    _write_json_atomic(COMPETITOR_MAPPING_FILE, db)


def _runs(discovery: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = discovery.get("runs") if isinstance(discovery.get("runs"), dict) else {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill legacy competitor discovery run states from JSON document into pim_workflow_runs."
    )
    parser.add_argument("--apply", action="store_true", help="Write rows. Without this flag the script only reports counts.")
    parser.add_argument(
        "--clear-json",
        action="store_true",
        help="After --apply, remove legacy discovery.runs from the JSON document.",
    )
    args = parser.parse_args()

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    runs = _runs(discovery)

    for run in runs.values():
        if args.apply:
            _persist_discovery_run(run)

    if args.apply and args.clear_json:
        if runs:
            discovery["runs"] = {}
            save_competitor_mapping_db(db)
        _clear_legacy_root_runs()

    mode = "applied" if args.apply else "dry-run"
    cleared = len(runs) if args.apply and args.clear_json else 0
    print(f"{mode}: runs={len(runs)}, json_runs_cleared={cleared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
