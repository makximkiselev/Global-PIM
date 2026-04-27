import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath("backend"))

from app.core.products import service as products_service


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


if __name__ == "__main__":
    unittest.main()
