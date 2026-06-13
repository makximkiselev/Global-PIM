#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.api.routes.competitor_catalog_import import (  # noqa: E402
    CompetitorCatalogRunRequest,
    _crawl_site,
    _load_store,
    _public_product,
    _save_store,
)
from app.core.tenant_context import (  # noqa: E402
    reset_current_tenant_organization_id,
    set_current_tenant_organization_id,
)
from app.core.json_store import with_lock  # noqa: E402


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    token = set_current_tenant_organization_id(args.organization_id)
    try:
        if args.input_file:
            payload = json.loads(Path(args.input_file).read_text(encoding="utf-8"))
            run = payload.get("run") if isinstance(payload, dict) else {}
            products = payload.get("products") if isinstance(payload, dict) else []
            if not isinstance(run, dict) or not isinstance(products, list):
                raise RuntimeError("BAD_INPUT_FILE")
            return _save_result(args, run, [product for product in products if isinstance(product, dict)])
        request = CompetitorCatalogRunRequest(
            name=args.name or args.start_url,
            start_url=args.start_url,
            max_pages=args.max_pages,
            max_products=args.max_products,
        )
        run, products = await _crawl_site(request)
        if args.output_file:
            Path(args.output_file).write_text(
                json.dumps({"run": run, "products": products}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if args.no_save:
            return {
                "run": run,
                "saved_products": 0,
                "total_products_in_store": 0,
                "preview": products[:5],
            }
        return _save_result(args, run, products)
    finally:
        reset_current_tenant_organization_id(token)


def _save_result(args: argparse.Namespace, run: dict[str, Any], products: list[dict[str, Any]]) -> dict[str, Any]:
    lock = with_lock(f"competitor_catalog_imports:{args.organization_id}")
    if not lock.acquire(timeout=30):
        raise RuntimeError("STORE_LOCKED")
    try:
        store = _load_store()
        store["runs"][run["id"]] = run
        for product in products:
            store["products"][product["id"]] = product
        _save_store(store)
    finally:
        lock.release()
    store = _load_store()
    return {
        "run": run,
        "saved_products": len(products),
        "total_products_in_store": len(store.get("products") or {}),
        "preview": [_public_product(product, store) for product in products[:5]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a bounded competitor catalog into the current SmartPim tenant store.")
    parser.add_argument("--organization-id", default=os.getenv("PIM_ORGANIZATION_ID", "org_default"))
    parser.add_argument("--name", default="")
    parser.add_argument("--start-url", default="")
    parser.add_argument("--max-pages", type=int, default=int(os.getenv("COMPETITOR_CATALOG_IMPORT_PAGES", "5000") or "5000"))
    parser.add_argument("--max-products", type=int, default=int(os.getenv("COMPETITOR_CATALOG_IMPORT_PRODUCTS", "20000") or "20000"))
    parser.add_argument("--output-file", default="", help="Write crawled run/products JSON to this path.")
    parser.add_argument("--input-file", default="", help="Merge a previously crawled run/products JSON file into the tenant store.")
    parser.add_argument("--no-save", action="store_true", help="Do not save crawled products to the tenant store.")
    args = parser.parse_args()
    if not args.input_file and not args.start_url:
        parser.error("--start-url is required unless --input-file is used")
    result = asyncio.run(_run(args))
    run = result["run"]
    print(
        "completed",
        f"id={run.get('id')}",
        f"host={run.get('host')}",
        f"pages={run.get('pages_scanned')}",
        f"products={run.get('products_found')}",
        f"errors={len(run.get('errors') or [])}",
        f"total_store={result.get('total_products_in_store')}",
        flush=True,
    )
    for error in (run.get("errors") or [])[:10]:
        print("error", error, flush=True)
    for product in result["preview"]:
        print("preview", product.get("title"), product.get("url"), flush=True)


if __name__ == "__main__":
    main()
