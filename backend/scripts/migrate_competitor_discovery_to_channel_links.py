#!/usr/bin/env python3
from __future__ import annotations

import argparse
from typing import Any, Dict

from app.api.routes.competitor_mapping import (
    _ensure_discovery_doc,
    _persist_competitor_channel_candidate,
    _persist_competitor_channel_link,
)
from app.storage.json_store import (
    COMPETITOR_MAPPING_FILE,
    DEFAULT_COMPETITOR_MAPPING,
    _read_json,
    _write_json_atomic,
    load_competitor_mapping_db,
    save_competitor_mapping_db,
)


def _clear_legacy_root_discovery() -> None:
    db = _read_json(COMPETITOR_MAPPING_FILE, DEFAULT_COMPETITOR_MAPPING)
    if not isinstance(db, dict):
        return
    discovery = _ensure_discovery_doc(db)
    changed = bool((discovery.get("candidates") or {}) or (discovery.get("links") or {}))
    if not changed:
        return
    discovery["candidates"] = {}
    discovery["links"] = {}
    _write_json_atomic(COMPETITOR_MAPPING_FILE, db)


def _candidate_by_id(discovery: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = discovery.get("candidates") if isinstance(discovery.get("candidates"), dict) else {}
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill competitor discovery candidates/links from legacy JSON document into pim_channel_links."
    )
    parser.add_argument("--apply", action="store_true", help="Write rows. Without this flag the script only reports counts.")
    parser.add_argument(
        "--clear-json",
        action="store_true",
        help="After --apply, remove legacy discovery.candidates and discovery.links from the JSON document.",
    )
    args = parser.parse_args()

    db = load_competitor_mapping_db()
    discovery = _ensure_discovery_doc(db)
    candidates = _candidate_by_id(discovery)
    links = discovery.get("links") if isinstance(discovery.get("links"), dict) else {}

    candidate_count = 0
    link_count = 0

    for candidate in candidates.values():
        candidate_count += 1
        if args.apply:
            _persist_competitor_channel_candidate(candidate)

    for link in links.values():
        if not isinstance(link, dict):
            continue
        link_count += 1
        candidate = candidates.get(str(link.get("candidate_id") or ""))
        if args.apply:
            _persist_competitor_channel_link(link, candidate)

    if args.apply and args.clear_json:
        if candidates or links:
            discovery["candidates"] = {}
            discovery["links"] = {}
            save_competitor_mapping_db(db)
        _clear_legacy_root_discovery()

    mode = "applied" if args.apply else "dry-run"
    cleared_candidates = candidate_count if args.apply and args.clear_json else 0
    cleared_links = link_count if args.apply and args.clear_json else 0
    print(
        f"{mode}: candidates={candidate_count}, links={link_count}, "
        f"json_candidates_cleared={cleared_candidates}, json_links_cleared={cleared_links}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
