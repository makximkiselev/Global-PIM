import os
import sys
import unittest
from unittest.mock import patch

from fastapi.encoders import jsonable_encoder

sys.path.insert(0, os.path.abspath("backend"))

from app.core.products import service as products_service
from app.core.products import parameter_flow
from app.storage import relational_pim_store


class ProductServiceTests(unittest.TestCase):
    def test_get_product_service_loads_variants_only_from_same_group(self) -> None:
        product = {
            "id": "product_70",
            "title": "Product 70",
            "group_id": "group_47",
        }
        variants = [
            {"id": "product_71", "title": "Variant 1", "group_id": "group_47"},
            {"id": "product_72", "title": "Variant 2", "group_id": "group_47"},
            {"id": "product_70", "title": "Self", "group_id": "group_47"},
        ]

        with (
            patch.object(products_service, "load_products_by_ids", return_value=[product]) as load_by_ids,
            patch.object(products_service, "load_products_by_group", return_value=variants) as load_by_group,
            patch.object(products_service, "_info_model_context_for_category", return_value={"has_template": False}) as info_model_context,
        ):
            payload = products_service.get_product_service("product_70", include_variants=True)

        load_by_ids.assert_called_once_with(["product_70"])
        load_by_group.assert_called_once_with("group_47")
        info_model_context.assert_called_once_with("")
        self.assertEqual(payload["product"]["id"], "product_70")
        self.assertEqual([item["id"] for item in payload["variants"]], ["product_71", "product_72"])
        self.assertEqual(payload["info_model"], {"has_template": False})

    def test_product_service_reports_missing_info_model_separately_from_saved_features(self) -> None:
        product = {
            "id": "product_1",
            "category_id": "phones",
            "content": {"features": [{"code": "processor", "name": "Процессор", "value": "A18 Pro"}]},
        }

        with (
            patch.object(products_service, "load_products_by_ids", return_value=[product]),
            patch.object(products_service, "load_templates_db_doc", return_value={"templates": {}, "attributes": {}, "category_to_templates": {}}),
            patch.object(products_service, "load_category_template_resolution_map", return_value={"phones": {"template_id": ""}}),
        ):
            payload = products_service.get_product_service("product_1", include_variants=False)

        self.assertEqual(payload["product"]["content"]["features"][0]["code"], "processor")
        self.assertFalse(payload["info_model"]["has_template"])
        self.assertEqual(payload["info_model"]["attributes_count"], 0)

    def test_product_service_reports_info_model_attributes_for_category(self) -> None:
        product = {"id": "product_1", "category_id": "phones"}
        templates_db = {
            "templates": {"tpl-phone": {"id": "tpl-phone", "name": "Phone model", "meta": {"info_model": {"status": "approved"}}}},
            "attributes": {"tpl-phone": [{"code": "processor", "name": "Процессор", "required": True}]},
            "category_to_templates": {"phones": ["tpl-phone"]},
        }

        with (
            patch.object(products_service, "load_products_by_ids", return_value=[product]),
            patch.object(products_service, "load_templates_db_doc", return_value=templates_db),
        ):
            payload = products_service.get_product_service("product_1", include_variants=False)

        self.assertTrue(payload["info_model"]["has_template"])
        self.assertEqual(payload["info_model"]["template_id"], "tpl-phone")
        self.assertEqual(payload["info_model"]["attributes_count"], 1)
        self.assertEqual(payload["info_model"]["attributes"][0]["code"], "processor")

    def test_product_normalizer_does_not_nest_extra_on_readback(self) -> None:
        raw = {
            "id": "product_1",
            "category_id": "phones",
            "title": "Apple iPhone",
            "status": "archive",
            "extra": {"extra": {"extra": {}}},
        }

        normalized = relational_pim_store._normalize_products_doc({"items": [raw]})
        item = normalized["items"][0]

        self.assertEqual(item["extra"], {})
        self.assertEqual(item["status"], "archived")
        jsonable_encoder({"product": item})

    def test_patch_product_service_stores_archived_status_canonically(self) -> None:
        product = {
            "id": "product_1",
            "category_id": "phones",
            "title": "Apple iPhone",
            "status": "active",
            "sku_gt": "50001",
        }

        with (
            patch.object(products_service, "query_products_full", return_value=[product]),
            patch.object(products_service, "upsert_product_item", side_effect=lambda item: item) as upsert_product,
        ):
            result = products_service.patch_product_service("product_1", {"status": "archive"})

        self.assertEqual(result["product"]["status"], "archived")
        upsert_product.assert_called_once()

    def test_delete_products_bulk_service_removes_existing_ids(self) -> None:
        with (
            patch.object(products_service, "load_products_by_ids", return_value=[{"id": "product_1"}]) as load_by_ids,
            patch.object(products_service, "delete_product_items", return_value=1) as delete_items,
        ):
            result = products_service.delete_products_bulk_service(["product_1"])

        load_by_ids.assert_called_once_with(["product_1"])
        delete_items.assert_called_once_with(["product_1"])
        self.assertEqual(result, {"ok": True, "deleted": 1, "ids": ["product_1"]})

    def test_parameter_flow_does_not_put_description_in_service_rows(self) -> None:
        product = {
            "id": "product_1",
            "category_id": "phones",
            "title": "Apple iPhone",
            "sku_gt": "50001",
            "content": {"description": "Long product description", "features": []},
        }

        with (
            patch.object(parameter_flow, "load_catalog_nodes", return_value=[]),
            patch.object(parameter_flow, "_load_attr_rows_by_category", return_value={}),
            patch.object(parameter_flow, "_load_value_refs_by_category", return_value={}),
        ):
            payload = parameter_flow.build_product_parameter_flow(product)

        self.assertNotIn("description", [row.get("code") for row in payload["service_rows"]])
        self.assertEqual(payload["items"], [])


if __name__ == "__main__":
    unittest.main()
