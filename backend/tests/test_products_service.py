import os
import sys
import unittest
from unittest.mock import patch

from fastapi.encoders import jsonable_encoder

sys.path.insert(0, os.path.abspath("backend"))

from app.core.products import service as products_service
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
        ):
            payload = products_service.get_product_service("product_70", include_variants=True)

        load_by_ids.assert_called_once_with(["product_70"])
        load_by_group.assert_called_once_with("group_47")
        self.assertEqual(payload["product"]["id"], "product_70")
        self.assertEqual([item["id"] for item in payload["variants"]], ["product_71", "product_72"])

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


if __name__ == "__main__":
    unittest.main()
