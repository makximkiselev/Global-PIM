import asyncio
import os
import sys
import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi import HTTPException


sys.path.insert(0, os.path.abspath("backend"))

from app.api.routes import catalog_exchange, competitor_mapping, templates, yandex_market
from app.api.routes.catalog_exchange import CatalogExportRunReq, CatalogImportRunReq
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
        saved_channel_links: list[dict[str, object]] = []

        def save(next_db):
            saved.clear()
            saved.update(deepcopy(next_db))

        with (
            patch.object(competitor_mapping, "load_competitor_mapping_db", return_value=deepcopy(db)),
            patch.object(competitor_mapping, "save_competitor_mapping_db", side_effect=save),
            patch.object(competitor_mapping, "upsert_pim_channel_link", side_effect=lambda row: saved_channel_links.append(deepcopy(row)) or row),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = competitor_mapping.moderate_candidate("candidate-a", {"action": "approve"})

        candidates = saved["discovery"]["candidates"]
        self.assertEqual(response["candidate"]["status"], "approved")
        self.assertEqual(candidates, {})
        by_id = {row["link_id"]: row for row in saved_channel_links}
        self.assertEqual(by_id["candidate-a"]["status"], "approved")
        self.assertEqual(by_id["candidate-b"]["status"], "rejected")
        self.assertEqual(by_id["candidate-b"]["payload"]["rejection_reason"], "sibling_not_selected")
        self.assertEqual(by_id["product_1:store77"]["url"], "https://store77.net/a")

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
        saved_channel_links: list[dict[str, object]] = []

        async def fake_extract(url):
            self.assertEqual(url, "https://store77.net/meta-quest-3-128")
            return {
                "ok": True,
                "source_id": "store77",
                "title": "Meta Quest 3 128GB",
                "description": "VR headset with 128GB storage",
                "images": ["https://store77.net/images/meta-quest-3-128.jpg"],
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
            patch.object(competitor_mapping, "upsert_pim_channel_link", side_effect=lambda row: saved_channel_links.append(deepcopy(row)) or row),
            patch.object(competitor_mapping, "extract_competitor_content", side_effect=fake_extract),
            patch.object(competitor_mapping, "_import_competitor_image_to_storage", return_value={
                "url": "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg",
                "external_url": "https://store77.net/images/meta-quest-3-128.jpg",
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(competitor_mapping, "now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = asyncio.run(competitor_mapping.enrich_product_from_confirmed_competitors("product_1"))

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["enriched_sources"], ["store77"])
        self.assertIn("product", response)
        content = response["product"]["content"]
        self.assertEqual(content["description"], "VR headset with 128GB storage")
        self.assertEqual(content["media_images"][0]["url"], "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg")
        self.assertEqual(content["media_images"][0]["external_url"], "https://store77.net/images/meta-quest-3-128.jpg")
        self.assertEqual(content["media_images"][0]["storage"], "s3")
        self.assertEqual(content["media_images"][0]["role"], "gallery")
        self.assertEqual(content["media_images"][0]["selected"], True)
        self.assertEqual(content["media_images"][0]["status"], "ready")
        self.assertEqual(content["competitor_links"]["store77"]["url"], "https://store77.net/meta-quest-3-128")
        self.assertEqual(content["competitor_links"]["store77"]["status"], "confirmed")
        self.assertEqual(content["source_values"]["media_images"]["store77"]["count"], 1)
        self.assertTrue(
            any((row.get("payload") or {}).get("last_enriched_at") == "2026-04-27T12:00:00+00:00" for row in saved_channel_links)
        )
        self.assertEqual(saved_db["discovery"]["links"], {})

    def test_catalog_import_uses_confirmed_partner_links_before_export(self) -> None:
        req = CatalogImportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "use_yandex_market": False,
                "use_competitors": True,
                "limit": 10,
            }
        )
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "category_id": "cat-vr",
            "content": {"features": [], "description": "", "links": []},
        }
        competitor_db = {
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
        saved_products: list[dict[str, object]] = []

        async def fake_extract(url, **_kwargs):
            self.assertEqual(url, "https://store77.net/meta-quest-3-128")
            return {
                "description": "Partner description",
                "images": ["https://store77.net/images/meta-quest-3-128.jpg"],
                "specs": {},
            }

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_products", return_value=[deepcopy(product)]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[]),
            patch.object(catalog_exchange, "_resolve_template_id", return_value="tpl-vr"),
            patch.object(catalog_exchange, "load_competitor_mapping_db", return_value=deepcopy(competitor_db)),
            patch.object(catalog_exchange, "_extract_competitor_content_with_retry", side_effect=fake_extract),
            patch.object(catalog_exchange, "_import_competitor_image_to_storage", return_value={
                "url": "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg",
                "external_url": "https://store77.net/images/meta-quest-3-128.jpg",
                "content_type": "image/jpeg",
                "size": 123,
                "storage": "s3",
            }),
            patch.object(catalog_exchange, "_fetch_store77_images_with_browser", return_value={}),
            patch.object(catalog_exchange, "_save_products", side_effect=lambda items: saved_products.extend(deepcopy(items))),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", side_effect=lambda _path, _doc: None),
            patch.object(catalog_exchange, "_now_iso", return_value="2026-04-27T12:00:00+00:00"),
        ):
            response = asyncio.run(catalog_exchange.run_catalog_import(req))

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["import_overview"]["images_ready"], 1)
        self.assertEqual(response["import_overview"]["with_competitor_media"], 1)
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["url"], "/api/uploads/media_images/product_1/competitors/store77/meta-quest-3-128.jpg")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["external_url"], "https://store77.net/images/meta-quest-3-128.jpg")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["source"], "store77")
        self.assertEqual(saved_products[0]["content"]["media_images"][0]["storage"], "s3")

    def test_content_source_summary_detects_competitor_media_after_storage_import(self) -> None:
        product = {
            "id": "product_1",
            "content": {
                "media_images": [
                    {
                        "url": "/api/uploads/media_images/product_1/competitors/store77/image.jpg",
                        "external_url": "https://store77.net/images/image.jpg",
                        "source": "store77",
                        "storage": "s3",
                    }
                ],
                "source_values": {"media_images": {"store77": {"count": 1}}},
            },
        }

        summary = catalog_exchange._content_source_summary(product)

        self.assertEqual(summary["media"]["images_count"], 1)
        self.assertTrue(summary["media"]["from_competitors"])

    def test_export_media_url_expands_local_uploads_to_public_urls(self) -> None:
        with (
            patch.dict(os.environ, {"APP_PUBLIC_BASE_URL": "https://pim.id-smart.ru"}),
            patch.object(yandex_market, "_env_file_value", return_value=""),
        ):
            self.assertEqual(
                yandex_market._export_media_url("/api/uploads/media_images/product_1/image.jpg"),
                "https://pim.id-smart.ru/api/uploads/media_images/product_1/image.jpg",
            )
            self.assertEqual(
                yandex_market._export_media_url("https://cdn.example.test/image.jpg"),
                "https://cdn.example.test/image.jpg",
            )

    def test_store77_discovery_scans_real_category_before_seed_fallback(self) -> None:
        product = {
            "id": "product_1",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "sku_gt": "52460",
            "category_id": "phones",
        }
        html = """
        <a href="/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/">
          Телефон Apple iPhone 17 Pro 256 ГБ, eSim (электронная SIM-карта), цвет: серебристый (Silver)
        </a>
        """
        fetched_urls: list[str] = []

        async def fake_fetch(url):
            fetched_urls.append(url)
            return html

        with patch.object(competitor_mapping, "_fetch_store77_category_html", side_effect=fake_fetch):
            candidates = asyncio.run(competitor_mapping._discover_store77_candidates(product))

        self.assertEqual(candidates[0]["url"], "https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/")
        self.assertIn("apple_iphone_17_pro_1", fetched_urls[0])
        self.assertEqual(len(fetched_urls), 1)
        self.assertTrue(all("/product/product_" not in item["url"] for item in candidates))

    def test_store77_seed_candidate_requires_matching_product_page(self) -> None:
        candidate = {
            "title": "Телефон Apple iPhone 17 Pro 256Gb eSim (Silver)",
            "url": "https://store77.net/apple_iphone_17_pro_1/telefon_apple_iphone_17_pro_256gb_esim_silver/",
        }
        self.assertTrue(
            competitor_mapping._store77_seed_candidate_matches_page(
                candidate,
                "Телефон Apple iPhone 17 Pro 256 ГБ eSim цвет серебристый Silver",
            )
        )
        self.assertFalse(
            competitor_mapping._store77_seed_candidate_matches_page(
                candidate,
                "Чехол Gurdini Super Slim для iPhone 17 Pro",
            )
        )

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
            patch.object(catalog_exchange.ConnectorsStateReadAdapter, "import_stores", side_effect=lambda provider: {
                "yandex_market": [{"id": "ym-1", "title": "YM", "enabled": True}],
                "ozon": [{"id": "oz-1", "title": "Ozon", "enabled": True}],
            }.get(provider, [])),
            patch.object(catalog_exchange, "yandex_export_preview", return_value={
                "ready_count": 1,
                "count": 1,
                "items": [{"product_id": "product_1", "ready": True, "missing": []}],
            }),
            patch.object(catalog_exchange, "_ozon_export_preview", return_value={
                "ready_count": 0,
                "count": 1,
                "items": [{"product_id": "product_1", "product_title": "Meta Quest 3 128GB", "category_id": "cat-vr", "ready": False, "missing": ["description"]}],
            }),
            patch.object(catalog_exchange, "_load_runs", return_value={"runs": {}}),
            patch.object(catalog_exchange, "_save_runs", side_effect=lambda _path, doc: saved_runs.update(deepcopy(doc))),
            patch.object(catalog_exchange, "uuid4", return_value=type("FakeUuid", (), {"hex": "abcdef1234567890"})()),
        ):
            response = catalog_exchange.run_catalog_export(req)

        self.assertEqual(response["ok"], True)
        self.assertEqual(response["count"], 1)
        self.assertEqual(
            response["summary"],
            {
                "product_count": 1,
                "target_count": 2,
                "batch_count": 2,
                "ready_batches": 1,
                "blocked_batches": 1,
                "ready_target_items": 1,
                "blocked_target_items": 1,
                "blockers_count": 1,
                "status": "blocked",
            },
        )
        self.assertEqual(len(response["batches"]), 2)
        self.assertEqual(response["batches"][0]["provider"], "yandex_market")
        self.assertEqual(response["batches"][0]["status"], "ready")
        self.assertEqual(response["batches"][0]["ready_count"], 1)
        self.assertEqual(response["batches"][1]["provider"], "ozon")
        self.assertEqual(response["batches"][1]["status"], "blocked")
        self.assertEqual(response["batches"][1]["ready_count"], 0)
        self.assertEqual(response["batches"][1]["not_ready_count"], 1)
        self.assertEqual(response["batches"][1]["blockers_count"], 1)
        self.assertEqual(response["batches"][1]["items"][0]["missing"], ["description"])
        self.assertEqual(response["batches"][1]["blockers"][0]["missing"], ["description"])
        self.assertEqual(response["batches"][1]["blockers"][0]["product_title"], "Meta Quest 3 128GB")
        self.assertEqual(response["batches"][1]["blockers"][0]["category_id"], "cat-vr")
        self.assertIn("export_abcdef1234", saved_runs["runs"])
        self.assertEqual(saved_runs["runs"]["export_abcdef1234"]["summary"]["blocked_target_items"], 1)

    def test_export_run_rejects_unknown_selected_store_id(self) -> None:
        req = CatalogExportRunReq.model_validate(
            {
                "selection": {"node_ids": [], "product_ids": ["product_1"], "include_descendants": False},
                "targets": [{"provider": "yandex_market", "store_ids": ["gt_usd"]}],
                "limit": 20,
            }
        )

        with (
            patch.object(catalog_exchange, "_resolve_products", return_value=[{"id": "product_1", "title": "Meta Quest 3 128GB"}]),
            patch.object(
                catalog_exchange.ConnectorsStateReadAdapter,
                "import_stores",
                return_value=[{"id": "ym-store-real", "title": "GT USD", "enabled": True}],
            ),
            patch.object(catalog_exchange, "yandex_export_preview", return_value={"ready_count": 1, "count": 1, "items": []}),
        ):
            with self.assertRaises(HTTPException) as ctx:
                catalog_exchange.run_catalog_export(req)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("No matching stores selected", str(ctx.exception.detail))

    def test_ozon_export_preview_derives_required_type_and_model_name(self) -> None:
        product = {
            "id": "product_iphone",
            "sku_gt": "52460",
            "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)",
            "category_id": "cat-iphone",
            "content": {
                "media_images": [{"url": "/api/uploads/media_images/iphone.webp"}],
                "description": "Apple iPhone 17 Pro",
                "features": [
                    {"code": "brand", "name": "Бренд", "value": "Apple"},
                    {"code": "camera_type", "name": "Тип основных камер", "value": "телефото"},
                ],
            },
        }

        rows = [
            {
                "catalog_name": "Тип основных камер",
                "provider_map": {
                    "ozon": {"id": "8229", "name": "Тип", "required": True, "export": True}
                },
            },
            {
                "catalog_name": "Бренд",
                "provider_map": {
                    "ozon": {"id": "85", "name": "Бренд", "required": True, "export": True}
                },
            },
        ]

        with (
            patch.object(catalog_exchange, "query_products_full", return_value=[product]),
            patch.object(catalog_exchange, "_load_nodes", return_value=[{"id": "cat-iphone", "parent_id": None, "name": "Смартфоны"}]),
            patch.object(catalog_exchange, "_load_category_mapping", return_value={"cat-iphone": {"ozon": "17028922"}}),
            patch.object(catalog_exchange, "_load_attr_mapping_rows", return_value={"cat-iphone": rows}),
        ):
            response = catalog_exchange._ozon_export_preview(["product_iphone"], 10)

        self.assertEqual(response["ready_count"], 1)
        item = response["items"][0]
        self.assertEqual(item["missing"], [])
        attrs = {str(attr["id"]): attr["values"][0]["value"] for attr in item["payload_item"]["attributes"]}
        self.assertEqual(attrs["8229"], "Смартфон")
        self.assertEqual(attrs["9048"], "iPhone 17 Pro")

    def test_yandex_export_preview_filters_products_in_sql_by_selected_ids(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {"features": [{"code": "brand", "name": "Бренд", "value": "Meta"}]},
        }

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]) as query_mock,
            patch.object(yandex_market, "_load_products", side_effect=AssertionError("must not load full product table")),
            patch.object(yandex_market, "_load_nodes", return_value=[]),
            patch.object(yandex_market, "_load_category_mapping", return_value={}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        query_mock.assert_called_once_with(ids=["product_1"])
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["items"][0]["payload_item"]["offerId"], "GT-1")
        self.assertEqual(response["items"][0]["product_title"], "Meta Quest 3 128GB")
        self.assertEqual(response["items"][0]["category_id"], "cat-vr")

    def test_yandex_export_preview_treats_description_and_media_as_system_content(self) -> None:
        product = {
            "id": "product_1",
            "title": "Meta Quest 3 128GB",
            "sku_gt": "GT-1",
            "category_id": "cat-vr",
            "status": "active",
            "content": {
                "description": "VR headset",
                "media_images": [{"url": "https://cdn.example.test/quest.jpg"}],
                "features": [{"code": "brand", "name": "Бренд", "value": "Meta"}],
            },
        }

        with (
            patch.object(yandex_market, "query_products_full", return_value=[deepcopy(product)]),
            patch.object(yandex_market, "_load_nodes", return_value=[]),
            patch.object(yandex_market, "_load_category_mapping", return_value={"cat-vr": {"yandex_market": "ym-vr"}}),
            patch.object(yandex_market, "_load_attr_mapping_rows", return_value={}),
            patch.object(yandex_market, "_load_attr_value_refs", return_value={}),
            patch.object(yandex_market, "_yandex_required_param_ids", return_value=set()),
        ):
            response = yandex_market.yandex_export_preview(
                yandex_market.ExportPreviewReq(product_ids=["product_1"], only_active=False, limit=10)
            )

        missing = response["items"][0]["missing"]
        self.assertNotIn("Не настроен блок 'Медиа' для Я.Маркет в маппинге", missing)
        self.assertNotIn("Не настроен блок 'Описание товара' для Я.Маркет в маппинге", missing)
        self.assertNotIn("Нет изображений (pictures)", missing)
        self.assertNotIn("Описание (аннотация) не заполнено", missing)
        self.assertEqual(response["items"][0]["payload_item"]["pictures"], ["https://cdn.example.test/quest.jpg"])
        self.assertEqual(response["items"][0]["payload_item"]["description"], "VR headset")

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
