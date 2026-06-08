from __future__ import annotations

from types import SimpleNamespace

from app.core.catalog_export_service import CatalogExportRunDeps, build_catalog_export_run


class _Dumpable(SimpleNamespace):
    def model_dump(self):
        return dict(self.__dict__)


def test_build_catalog_export_run_orchestrates_targets_and_persists_run():
    saved_runs: list[dict] = []

    async def enrich_candidate_media(products):
        return set()

    async def hydrate_marketplace_content(product_ids, targets, limit):
        return [{"provider": "yandex_market", "count": 1}]

    req = _Dumpable(
        selection=_Dumpable(node_ids=[], product_ids=["p1"], include_descendants=False),
        targets=[_Dumpable(provider="yandex_market", store_ids=["store_1"])],
        limit=10,
    )

    class Connectors:
        def import_stores(self, provider: str):
            assert provider == "yandex_market"
            return [{"id": "store_1", "title": "GT USD"}]

    deps = CatalogExportRunDeps(
        resolve_products=lambda node_ids, product_ids, include_descendants, limit: [{"id": "p1", "title": "Phone"}],
        enrich_candidate_media=enrich_candidate_media,
        hydrate_marketplace_content=hydrate_marketplace_content,
        hydrate_variant_siblings=lambda products: [],
        save_products=lambda products: None,
        query_products_by_ids=lambda product_ids: [{"id": "p1"}],
        query_products_for_sibling_hydration=lambda products: products,
        connectors_state_factory=Connectors,
        yandex_preview=lambda product_ids, limit: {"items": [{"product_id": "p1", "ready": True}]},
        ozon_preview=lambda product_ids, limit: {"items": []},
        selected_export_stores=lambda provider, stores, selected: stores,
        export_batch_from_preview=lambda **kwargs: {
            "provider": kwargs["provider"],
            "store_id": kwargs["store"]["id"],
            "status": "ready",
            "ready_count": 1,
            "not_ready_count": 0,
            "blockers_count": 0,
            "items": kwargs["preview"]["items"],
        },
        summarize_export_batches=lambda product_ids, batches: {"product_count": len(product_ids), "target_count": len(batches), "status": "ready"},
        load_runs=lambda: {"runs": {}},
        save_runs=lambda runs: saved_runs.append(runs),
        now_iso=lambda: "2026-06-07T10:00:00+00:00",
    )

    result = build_catalog_export_run(req, deps)

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["summary"] == {"product_count": 1, "target_count": 1, "status": "ready"}
    assert result["batches"][0]["store_id"] == "store_1"
    run = next(iter(saved_runs[0]["runs"].values()))
    assert run["selection"] == {"node_ids": [], "product_ids": ["p1"], "include_descendants": False}
    assert run["marketplace_hydration"] == [{"provider": "yandex_market", "count": 1}]


def test_build_catalog_export_run_hydrates_selected_products_with_sibling_context():
    hydrated_ids: list[list[str]] = []
    preview_ids: list[list[str]] = []
    saved_products: list[list[dict]] = []

    async def enrich_candidate_media(products):
        return set()

    async def hydrate_marketplace_content(product_ids, targets, limit):
        return []

    def hydrate_variant_siblings(products):
        hydrated_ids.append([str(product.get("id") or "") for product in products])
        return [{"id": "p1", "content": {"features": [{"code": "package_weight", "value": "320"}]}}]

    req = _Dumpable(
        selection=_Dumpable(node_ids=[], product_ids=["p1"], include_descendants=False),
        targets=[_Dumpable(provider="ozon", store_ids=["store_1"])],
        limit=10,
    )

    class Connectors:
        def import_stores(self, provider: str):
            assert provider == "ozon"
            return [{"id": "store_1", "title": "Ozon"}]

    deps = CatalogExportRunDeps(
        resolve_products=lambda node_ids, product_ids, include_descendants, limit: [{"id": "p1", "title": "Phone"}],
        enrich_candidate_media=enrich_candidate_media,
        hydrate_marketplace_content=hydrate_marketplace_content,
        hydrate_variant_siblings=hydrate_variant_siblings,
        save_products=lambda products: saved_products.append(products),
        query_products_by_ids=lambda product_ids: [{"id": "p1"}],
        query_products_for_sibling_hydration=lambda products: [{"id": "p1"}, {"id": "p2"}],
        connectors_state_factory=Connectors,
        yandex_preview=lambda product_ids, limit: {"items": []},
        ozon_preview=lambda product_ids, limit: preview_ids.append(product_ids) or {"items": [{"product_id": "p1", "ready": True}]},
        selected_export_stores=lambda provider, stores, selected: stores,
        export_batch_from_preview=lambda **kwargs: {
            "provider": kwargs["provider"],
            "store_id": kwargs["store"]["id"],
            "status": "ready",
            "ready_count": 1,
            "not_ready_count": 0,
            "blockers_count": 0,
            "items": kwargs["preview"]["items"],
        },
        summarize_export_batches=lambda product_ids, batches: {"product_count": len(product_ids), "target_count": len(batches), "status": "ready"},
        load_runs=lambda: {"runs": {}},
        save_runs=lambda runs: None,
        now_iso=lambda: "2026-06-07T10:00:00+00:00",
    )

    result = build_catalog_export_run(req, deps)

    assert result["ok"] is True
    assert hydrated_ids == [["p1", "p2"]]
    assert preview_ids == [["p1"]]
    assert saved_products and saved_products[0][0]["id"] == "p1"
    assert result["marketplace_hydration"] == [{"provider": "variant_sibling", "updated_products": 1, "count": 1}]
