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
            patch.object(templates, "ensure_global_attribute", side_effect=lambda title, type_, code, scope: {"id": f"attr-{code}", "dict_id": f"dict-{code}"}),
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

    def test_info_model_draft_from_products_creates_candidates_with_provenance(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        products = [
            {
                "id": "product_quest_128",
                "category_id": "cat-vr",
                "title": "Meta Quest 3 128GB",
                "content": {
                    "features": [
                        {"name": "Бренд", "value": "Meta"},
                        {"name": "Встроенная память", "value": "128 GB"},
                    ]
                },
            },
            {
                "id": "product_quest_256",
                "category_id": "cat-vr",
                "title": "Meta Quest 3 256GB",
                "content": {
                    "features": [
                        {"name": "Бренд", "value": "Meta"},
                        {"name": "Встроенная память", "value": "256 GB"},
                    ]
                },
            },
        ]
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=deepcopy(products)),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-vr", "cand-brand", "cand-memory"]),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-vr", {"sources": ["products"]})

        self.assertEqual(response["template"]["id"], "tpl-draft-vr")
        self.assertEqual(response["info_model"]["status"], "draft")
        names = {candidate["name"] for candidate in response["candidates"]}
        self.assertIn("Бренд", names)
        self.assertIn("Встроенная память", names)
        memory = next(candidate for candidate in response["candidates"] if candidate["name"] == "Встроенная память")
        self.assertEqual(memory["examples"], ["128 GB", "256 GB"])
        self.assertEqual(memory["sources"][0]["kind"], "product")
        self.assertEqual(saved["templates"]["tpl-draft-vr"]["meta"]["info_model"]["status"], "draft")

    def test_info_model_draft_from_marketplaces_creates_channel_candidates(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            path_text = str(path)
            if path_text.endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-smart-ring": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "brand", "name": "Бренд", "required": True, "type": "ENUM", "values": [{"name": "Oura"}]},
                                        {"id": "ring_size", "name": "Размер кольца", "required": True, "type": "ENUM", "values": [{"name": "10"}]},
                                    ]
                                }
                            }
                        }
                    }
                }
            if path_text.endswith("category_attributes.json"):
                return {
                    "items": {
                        "ozon-smart-ring": {
                            "attributes": [
                                {"id": "battery", "name": "Время работы", "is_required": False, "type": "String"},
                                {"id": "ring_size", "name": "Размер кольца", "is_required": True, "type": "String"},
                            ]
                        }
                    }
                }
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(draft_service, "load_catalog_nodes", return_value=[{"id": "cat-rings", "parent_id": None, "name": "Умные кольца"}]),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-rings": {"yandex_market": "ym-smart-ring", "ozon": "ozon-smart-ring"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-rings", "cand-brand", "cand-size-ym", "cand-battery", "cand-size-ozon"]),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-rings", {"sources": ["marketplaces"]})

        names = {candidate["name"] for candidate in response["candidates"]}
        self.assertIn("Бренд", names)
        self.assertIn("Размер кольца", names)
        self.assertIn("Время работы", names)
        ring_size = next(candidate for candidate in response["candidates"] if candidate["name"] == "Размер кольца")
        self.assertEqual(ring_size["status"], "accepted")
        self.assertEqual({source["provider"] for source in ring_size["sources"]}, {"yandex_market", "ozon"})
        self.assertEqual(saved["templates"]["tpl-draft-rings"]["meta"]["info_model"]["draft_sources"], ["marketplaces"])

    def test_info_model_draft_uses_nearest_ancestor_marketplace_mapping(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {"templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        def read_doc(path, default=None):
            if str(path).endswith("category_parameters.json"):
                return {
                    "items": {
                        "ym-smart-rings": {
                            "raw": {
                                "result": {
                                    "parameters": [
                                        {"id": "ring_size", "name": "Размер кольца", "required": True, "type": "ENUM", "values": [{"name": "10"}]},
                                    ]
                                }
                            }
                        }
                    }
                }
            if str(path).endswith("category_attributes.json"):
                return {"items": {}}
            return deepcopy(default)

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "query_products_full", return_value=[]),
            patch.object(
                draft_service,
                "load_catalog_nodes",
                return_value=[
                    {"id": "cat-rings", "parent_id": None, "name": "Умные кольца"},
                    {"id": "cat-oura", "parent_id": "cat-rings", "name": "Oura Ring 4"},
                ],
            ),
            patch.object(draft_service, "load_category_mappings", return_value={"cat-rings": {"yandex_market": "ym-smart-rings"}}),
            patch.object(draft_service, "read_doc", side_effect=read_doc),
            patch.object(draft_service, "new_id", side_effect=["tpl-draft-oura", "cand-size"]),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T00:00:00+00:00"),
        ):
            response = draft_service.create_draft_from_sources("cat-oura", {"sources": ["marketplaces"]})

        self.assertEqual(response["template"]["id"], "tpl-draft-oura")
        self.assertEqual([candidate["name"] for candidate in response["candidates"]], ["Размер кольца"])
        self.assertEqual(saved["templates"]["tpl-draft-oura"]["meta"]["info_model"]["status"], "draft")

    def test_info_model_approve_draft_writes_accepted_candidates_to_attributes(self) -> None:
        from app.core.info_models import draft_service

        templates_db = {
            "templates": {
                "tpl-draft-vr": {
                    "id": "tpl-draft-vr",
                    "category_id": "cat-vr",
                    "name": "Draft: VR",
                    "meta": {
                        "info_model": {
                            "status": "draft",
                            "candidates": [
                                {
                                    "id": "cand-memory",
                                    "name": "Встроенная память",
                                    "code": "vstroennaya_pamyat",
                                    "type": "select",
                                    "group": "Характеристики",
                                    "required": True,
                                    "confidence": 0.9,
                                    "status": "accepted",
                                    "examples": ["128 GB", "256 GB"],
                                    "sources": [],
                                },
                                {
                                    "id": "cand-weight",
                                    "name": "Вес",
                                    "code": "ves",
                                    "type": "number",
                                    "group": "Габариты",
                                    "required": False,
                                    "confidence": 0.4,
                                    "status": "rejected",
                                    "examples": ["515 г"],
                                    "sources": [],
                                },
                            ],
                        }
                    },
                }
            },
            "attributes": {"tpl-draft-vr": []},
            "category_to_template": {"cat-vr": "tpl-draft-vr"},
            "category_to_templates": {"cat-vr": ["tpl-draft-vr"]},
        }
        saved: dict[str, object] = {}

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(draft_service, "load_templates_db", return_value=deepcopy(templates_db)),
            patch.object(draft_service, "save_templates_db", side_effect=save),
            patch.object(draft_service, "new_id", return_value="attr-memory"),
            patch.object(draft_service, "now_iso", return_value="2026-04-27T01:00:00+00:00"),
        ):
            response = draft_service.approve_draft("tpl-draft-vr")

        self.assertEqual(response["info_model"]["status"], "approved")
        attrs = saved["attributes"]["tpl-draft-vr"]
        self.assertEqual(len(attrs), 1)
        self.assertEqual(attrs[0]["name"], "Встроенная память")
        self.assertEqual(attrs[0]["options"]["source_candidates"], ["cand-memory"])
        self.assertEqual(saved["templates"]["tpl-draft-vr"]["meta"]["info_model"]["approved_at"], "2026-04-27T01:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
