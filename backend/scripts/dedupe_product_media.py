#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.media import dedupe_media_items  # noqa: E402
from app.storage.relational_pim_store import bulk_upsert_product_items, query_products_full  # noqa: E402


def _source_key(item: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(item.get("source") or "").strip(),
        str(item.get("source_url") or "").strip(),
    )


def compact_media(images: Any, *, competitor_source_limit: int) -> List[Dict[str, Any]]:
    items = [item for item in images if isinstance(item, dict)] if isinstance(images, list) else []
    deduped = dedupe_media_items(items)
    out: List[Dict[str, Any]] = []
    source_counts: Dict[Tuple[str, str], int] = {}
    for item in deduped:
        key = _source_key(item)
        source = key[0]
        if source in {"restore", "store77"} and key[1]:
            count = source_counts.get(key, 0)
            if count >= competitor_source_limit:
                continue
            source_counts[key] = count + 1
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Dedupe and compact product media_images in Postgres.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Without this flag only prints a summary.")
    parser.add_argument("--competitor-source-limit", type=int, default=int(os.getenv("COMPETITOR_MEDIA_PER_SOURCE_LIMIT", "12")))
    args = parser.parse_args()
    source_limit = max(1, min(50, int(args.competitor_source_limit)))

    products = query_products_full()
    changed: List[Dict[str, Any]] = []
    removed_total = 0
    for product in products:
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        images = content.get("media_images") if isinstance(content.get("media_images"), list) else []
        compacted = compact_media(images, competitor_source_limit=source_limit)
        if compacted == images:
            continue
        next_product = {**product, "content": {**content, "media_images": compacted, "media": compacted}}
        changed.append(next_product)
        removed_total += len(images) - len(compacted)

    print(f"products={len(products)} changed={len(changed)} removed_media={removed_total} apply={args.apply}")
    for product in changed[:20]:
        content = product.get("content") if isinstance(product.get("content"), dict) else {}
        print(f"- {product.get('id')}: {product.get('title')} -> {len(content.get('media_images') or [])} images")

    if args.apply and changed:
        bulk_upsert_product_items(changed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
