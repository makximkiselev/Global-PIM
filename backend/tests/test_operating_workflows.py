import asyncio
import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import patch


sys.path.insert(0, os.path.abspath("backend"))

from app.api.routes import catalog_exchange, competitor_mapping, templates
from app.api.routes.catalog_exchange import CatalogExportRunReq
from app.core.products import service as products_service


class OperatingWorkflowTests(unittest.TestCase):
    def test_new_category_without_model_can_create_draft_template(self) -> None:
        db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(templates, "load_templates_db", return_value=deepcopy(db)),
            patch.object(templates, "save_templates_db", side_effect=save),
            patch.object(templates, "new_id", return_value="tpl-draft-quest"),
            patch.object(templates, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = templates.create_for_category("cat-vr", {"name": "Draft: VR headsets"})

        self.assertEqual(response["template"]["id"], "tpl-draft-quest")
        self.assertEqual(response["template"]["category_id"], "cat-vr")
        self.assertIn("tpl-draft-quest", saved["templates"])
        self.assertEqual(saved["category_to_template"]["cat-vr"], "tpl-draft-quest")
        self.assertEqual(saved["category_to_templates"]["cat-vr"], ["tpl-draft-quest"])
        self.assertGreater(len(saved["attributes"]["tpl-draft-quest"]), 0)

    def test_approved_model_product_creation_preserves_skeleton_and_variant_group(self) -> None:
        existing_products: list[dict[str, object]] = []
        saved_products: list[dict[str, object]] = []

        def save_product(product):
            saved = deepcopy(product)
            saved_products.append(saved)
            existing_products.append(saved)
            return saved

        with (
            patch.object(products_service, "query_products_full", side_effect=lambda: deepcopy(existing_products)),
            patch.object(products_service, "allocate_sku_pairs_service", side_effect=[
                {"items": [{"sku_pim": "1001", "sku_gt": "51001"}]},
                {"items": [{"sku_pim": "1002", "sku_gt": "51002"}]},
            ]),
            patch.object(products_service, "upsert_product_item", side_effect=save_product),
        ):
            first = products_service.create_product_service(
                {
                    "category_id": "cat-vr",
                    "type": "multi",
                    "title": "Meta Quest 3 128GB",
                    "group_id": "group-quest-3",
                    "selected_params": ["brand", "memory", "color"],
                    "feature_params": ["memory", "resolution"],
                    "exports_enabled": {"yandex_market": True, "ozon": True},
                }
            )
            second = products_service.create_product_service(
                {
                    "category_id": "cat-vr",
                    "type": "multi",
                    "title": "Meta Quest 3 256GB",
                    "group_id": "group-quest-3",
                    "selected_params": ["brand", "memory", "color"],
                    "feature_params": ["memory", "resolution"],
                    "exports_enabled": {"yandex_market": True, "ozon": True},
                }
            )

        self.assertEqual(first["group_id"], "group-quest-3")
        self.assertEqual(second["group_id"], "group-quest-3")
        self.assertEqual(first["selected_params"], ["brand", "memory", "color"])
        self.assertEqual(first["feature_params"], ["memory", "resolution"])
        self.assertEqual(first["exports_enabled"], {"yandex_market": True, "ozon": True})
        self.assertNotEqual(first["sku_gt"], second["sku_gt"])
        self.assertEqual(len(saved_products), 2)

    def test_competitor_candidate_approval_confirms_one_and_rejects_siblings(self) -> None:
        db = {
            "version": 2,
            "templates": {},
            "categories": {},
            "discovery": {
                "candidates": {
                    "candidate-a": {
                        "id": "candidate-a",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/a",
                        "status": "needs_review",
                        "match_group_key": "iphone-16-pro-128-natural",
                        "last_seen_at": "2026-04-27T00:00:00+00:00",
                    },
                    "candidate-b": {
                        "id": "candidate-b",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/b",
                        "status": "needs_review",
                        "match_group_key": "iphone-16-pro-128-natural",
                        "last_seen_at": "2026-04-27T00:00:00+00:00",
                    },
                },
                "links": {},
                "runs": {},
            },
        }
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value=deepcopy(db)),
            patch.object(competitor_mapping, "save_competitor_mapping_db", side_effect=save),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = competitor_mapping.moderate_candidate("candidate-a", {"action": "approve"})

        candidates = saved["discovery"]["candidates"]
        self.assertEqual(response["candidate"]["status"], "approved")
        self.assertEqual(candidates["candidate-a"]["status"], "approved")
        self.assertEqual(candidates["candidate-b"]["status"], "rejected")
        self.assertEqual(candidates["candidate-b"]["rejection_reason"], "sibling_not_selected")
        self.assertEqual(saved["discovery"]["links"]["product_1:store77"]["url"], "https://store77.net/a")

    def test_existing_catalog_enrichment_uses_confirmed_competitor_links(self) -> None:
        db = {
            "version": 2,
            "templates": {},
            "categories": {},
            "discovery": {
                "candidates": {},
                "links": {
                    "product_1:store77": {
                        "id": "product_1:store77",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/meta-quest-3-128",
                        "status": "confirmed",
                    }
                },
                "runs": {},
            },
        }
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "content": {"features": [], "description": "", "links": []},
        }
        saved_db: dict[str, object] = {}

        async def fake_extract(url):
            self.assertEqual(url, "https://store77.net/meta-quest-3-128")
            return {
                "ok": True,
                "source_id": "store77",
                "title": "Meta Quest 3 128GB",
                "description": "VR headset with 128GB storage",
                "specs": {"memory": "128GB", "brand": "Meta"},
            }

        def save(next_db):
            saved_db.clear()
            saved_db.update(deepcopy(next_db))

        with (
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value=deepcopy(db)),
            patch.object(competitor_mapping, "save_competitor_mapping_db", side_effect=save),
            patch.object(competitor_mapping, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(competitor_mapping, "upsert_product_item", side_effect=lambda p: deepcopy(p)),
            patch.object(competitor_mapping, "extract_competitor_content", side_effect=fake_extract),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = asyncio.run(competitor_mapping.enrich_product_from_confirmed_competitors("product_1"))

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["enriched_sources"], ["store77"])
        self.assertIn("product", response)
        self.assertEqual(saved_db["discovery"]["links"]["product_1:store77"]["last_enriched_at"], "2026-04-27T12:00:00+00:00")

    def test_export_preview_keeps_ready_and_blockers_per_marketplace(self) -> None:
        saved_runs: dict[str, object] = {}
        req = CatalogExportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "targets": [{"provider": "yandex_market", "store_ids": ["ym-1"]}, {"provider": "ozon", "store_ids": ["oz-1"]}],
                "limit": 20,
            }
        )

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(catalog_exchange, "read_doc", return_value={
                "providers": {
                    "yandex_market": {"import_stores": [{"id": "ym-1", "title": "YM", "enabled": True}]},
                    "ozon": {"import_stores": [{"id": "oz-1", "title": "Ozon", "enabled": True}]},
                }
            }),
            patch.object(catalog_exchange, "yandex_export_preview", return_value={
                "ready_count": 1,
                "count": 1,
                "items": [{"product_id": "product_1", "ready": True, "missing": []}],
            }),
            patch.object(catalog_exchange, "_ozon_export_preview", return_value={
                "ready_count": 0,
                "count": 1,
                "items": [{"product_id": "product_1", "ready": False, "missing": ["description"]}],
            }),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", side_effect=lambda _path, doc: saved_runs.update(deepcopy(doc))),
            patch.object(catalog_exchange, "uuid4", return_value=type("FakeUuid", (), {"hex": "abcdef1234567890"})()),
        ):
            response = catalog_exchange.run_catalog_export(req)

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["count"], 1)
        self.assertEqual(len(response["batches"]), 2)
        self.assertEqual(response["batches"][0]["provider"], "yandex_market")
        self.assertEqual(response["batches"][0]["ready_count"], 1)
        self.assertEqual(response["batches"][1]["provider"], "ozon")
        self.assertEqual(response["batches"][1]["ready_count"], 0)
        self.assertEqual(response["batches"][1]["items"][0]["missing"], ["description"])
        self.assertIn("export_abcdef1234", saved_runs["runs"])


if __name__ == "__main__":
    unittest.main()
