from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, List
from uuid import uuid4


@dataclass(frozen=True)
class CatalogExportRunDeps:
    resolve_products: Callable[[Any, Any, bool, int], List[Dict[str, Any]]]
    enrich_candidate_media: Callable[[List[Dict[str, Any]]], Any]
    hydrate_marketplace_content: Callable[[List[str], Any, int], Any]
    hydrate_variant_siblings: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]
    save_products: Callable[[List[Dict[str, Any]]], None]
    query_products_by_ids: Callable[[List[str]], List[Dict[str, Any]]]
    query_products_for_sibling_hydration: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]
    connectors_state_factory: Callable[[], Any]
    yandex_preview: Callable[[List[str], int], Dict[str, Any]]
    ozon_preview: Callable[[List[str], int], Dict[str, Any]]
    selected_export_stores: Callable[[str, List[Dict[str, Any]], set[str]], List[Dict[str, Any]]]
    export_batch_from_preview: Callable[..., Dict[str, Any]]
    summarize_export_batches: Callable[[List[str], List[Dict[str, Any]]], Dict[str, Any]]
    load_runs: Callable[[], Dict[str, Any]]
    save_runs: Callable[[Dict[str, Any]], None]
    now_iso: Callable[[], str]


def build_catalog_export_run(req: Any, deps: CatalogExportRunDeps) -> Dict[str, Any]:
    products = deps.resolve_products(
        req.selection.node_ids,
        req.selection.product_ids,
        bool(req.selection.include_descendants),
        int(req.limit),
    )
    products = products[: int(req.limit)]
    product_ids = [str(p.get("id") or "").strip() for p in products if str(p.get("id") or "").strip()]

    enriched_from_candidates: List[str] = []
    if product_ids:
        enriched_from_candidates = sorted(asyncio.run(deps.enrich_candidate_media(products)))

    marketplace_hydration: List[Dict[str, Any]] = []
    if product_ids:
        marketplace_hydration = asyncio.run(deps.hydrate_marketplace_content(product_ids, req.targets or [], int(req.limit)))
        sibling_context = deps.query_products_for_sibling_hydration(products)
        if not sibling_context:
            sibling_context = deps.query_products_by_ids(product_ids)
        sibling_updates = deps.hydrate_variant_siblings(sibling_context)
        if sibling_updates:
            deps.save_products(sibling_updates)
            marketplace_hydration.append(
                {
                    "provider": "variant_sibling",
                    "updated_products": len(sibling_updates),
                    "count": len(sibling_updates),
                }
            )

    connectors_state = deps.connectors_state_factory()
    batches: List[Dict[str, Any]] = []
    for target in req.targets or []:
        provider = str(target.provider or "").strip()
        selected_store_ids = {str(x or "").strip() for x in target.store_ids if str(x or "").strip()}
        if provider == "yandex_market":
            preview = deps.yandex_preview(product_ids, len(product_ids) or 1000)
            stores = connectors_state.import_stores("yandex_market")
            selected_stores = deps.selected_export_stores(provider, stores, selected_store_ids)
            for store in selected_stores:
                batches.append(deps.export_batch_from_preview(provider=provider, store=store, preview=preview))
        elif provider == "ozon":
            stores = connectors_state.import_stores("ozon")
            selected_stores = deps.selected_export_stores(provider, stores, selected_store_ids)
            preview = deps.ozon_preview(product_ids, len(product_ids) or 1000)
            for store in selected_stores:
                batches.append(deps.export_batch_from_preview(provider=provider, store=store, preview=preview))

    run_id = f"export_{uuid4().hex[:10]}"
    summary = deps.summarize_export_batches(product_ids, batches)
    runs = deps.load_runs()
    runs["runs"][run_id] = {
        "id": run_id,
        "created_at": deps.now_iso(),
        "selection": req.selection.model_dump(),
        "targets": [t.model_dump() for t in req.targets or []],
        "summary": summary,
        "batches": batches,
        "enriched_from_candidates": enriched_from_candidates,
        "marketplace_hydration": marketplace_hydration,
    }
    deps.save_runs(runs)
    return {
        "ok": True,
        "run_id": run_id,
        "count": len(product_ids),
        "summary": summary,
        "batches": batches,
        "enriched_from_candidates": enriched_from_candidates,
        "marketplace_hydration": marketplace_hydration,
    }
