import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.core import auth as auth_core
from app.api.routes import catalog as catalog_routes
from app.api.routes import connectors_status as connectors_status_routes
from app.api.routes import info_models as info_models_routes
from app.api.routes import marketplace_mapping as marketplace_mapping_routes
from app.api.routes import templates as templates_routes


class ApiReadSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.test_root = Path(self._tmp.name)
        self.data_dir = self.test_root / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "auth").mkdir(parents=True, exist_ok=True)
        self.doc_store: dict[str, object] = {}

        def fake_read_doc(path: Path, default=None):
            key = str(Path(path))
            if key not in self.doc_store:
                return deepcopy(default)
            return deepcopy(self.doc_store[key])

        def fake_write_doc(path: Path, data) -> None:
            self.doc_store[str(Path(path))] = deepcopy(data)

        self.env_patches = [
            patch.dict(
                os.environ,
                {
                    "AUTH_COOKIE_SECURE": "0",
                },
                clear=False,
            )
        ]
        self.attr_patches = [
            patch.object(auth_core, "DATA_DIR", self.data_dir),
            patch.object(auth_core, "AUTH_BASE_PATH", self.data_dir / "auth" / "access.json"),
            patch.object(auth_core, "AUTH_SESSIONS_PATH", self.data_dir / "auth" / "sessions.json"),
            patch.object(auth_core, "AUTH_EVENTS_PATH", self.data_dir / "auth" / "login_events.json"),
            patch.object(auth_core, "read_doc", side_effect=fake_read_doc),
            patch.object(auth_core, "write_doc", side_effect=fake_write_doc),
        ]

        for item in self.env_patches + self.attr_patches:
            item.start()
            self.addCleanup(item.stop)

        marketplace_mapping_routes._import_categories_cache["ts"] = 0.0
        marketplace_mapping_routes._import_categories_cache["payload"] = None
        self.client = TestClient(app)
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        login = self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})
        self.assertEqual(login.status_code, 200)

    def test_catalog_nodes_endpoint(self) -> None:
        payload = {
            "nodes": [
                {"id": "root", "name": "Root", "parent_id": None, "position": 0, "products_count": 0}
            ]
        }
        with patch.object(catalog_routes, "get_nodes_json", return_value=payload):
            response = self.client.get("/api/catalog/nodes")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_templates_list_endpoint(self) -> None:
        templates_db = {
            "templates": {
                "tpl-1": {
                    "id": "tpl-1",
                    "category_id": "cat-1",
                    "name": "Template 1",
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-02T00:00:00+00:00",
                }
            },
            "attributes": {"tpl-1": []},
        }
        with (
            patch.object(templates_routes, "load_templates_db", return_value=templates_db),
            patch.object(templates_routes, "_ensure_default_attrs", side_effect=lambda attrs: attrs),
            patch.object(templates_routes, "_template_master_payload", return_value={"id": "tpl-1", "features": []}),
        ):
            response = self.client.get("/api/templates/list")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(body["items"][0]["id"], "tpl-1")

    def test_marketplace_mapping_import_categories_endpoint(self) -> None:
        with (
            patch.object(
                marketplace_mapping_routes,
                "_persistent_cache_read",
                return_value=None,
            ),
            patch.object(
                marketplace_mapping_routes,
                "_persistent_cache_write",
                return_value=None,
            ),
            patch.object(
                marketplace_mapping_routes,
                "_load_catalog_nodes",
                return_value=[{"id": "cat-1", "name": "Категория", "parent_id": "", "position": 0}],
            ),
            patch.object(
                marketplace_mapping_routes,
                "_catalog_rows",
                return_value=[{"id": "cat-1", "name": "Категория", "path": "Категория", "is_leaf": True}],
            ),
            patch.object(
                marketplace_mapping_routes,
                "_load_mappings",
                return_value={"cat-1": {"yandex_market": "ym-1", "ozon": "oz-1"}},
            ),
            patch.object(
                marketplace_mapping_routes,
                "_load_provider_categories",
                side_effect=lambda provider: [{"id": f"{provider}-1", "name": provider, "path": provider}],
            ),
            patch.object(
                marketplace_mapping_routes,
                "_build_binding_states",
                return_value={"cat-1": {"mapped_children": 1, "total_children": 1}},
            ),
            patch.object(
                marketplace_mapping_routes,
                "_build_competitor_states",
                return_value={"cat-1": {"configured": True}},
            ),
        ):
            response = self.client.get("/api/marketplaces/mapping/import/categories")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertIn("catalog_nodes", body)
        self.assertIn("providers", body)
        self.assertIn("mappings", body)

    def test_connectors_status_endpoint(self) -> None:
        state = {
            "providers": {
                "yandex_market": {
                    "methods": {
                        "categories_tree": {
                            "schedule": "1h",
                            "status": "ok",
                            "last_run_at": None,
                        }
                    },
                    "settings": {"offer_id_source": "sku_gt"},
                    "import_stores": [],
                }
            }
        }
        with patch.object(connectors_status_routes, "_load_state", return_value=state):
            response = self.client.get("/api/connectors/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertIn("providers", body)

    def test_marketplace_mapping_attribute_bootstrap_endpoint(self) -> None:
        payload = {
            "ok": True,
            "items": [{"id": "cat-1", "name": "Категория"}],
            "count": 1,
            "catalog_attr_options": [],
            "service_param_defs": [],
        }
        with (
            patch.object(
                marketplace_mapping_routes,
                "_persistent_cache_read",
                return_value=None,
            ),
            patch.object(
                marketplace_mapping_routes,
                "_persistent_cache_write",
                return_value=None,
            ),
            patch.object(
                marketplace_mapping_routes,
                "mapping_attribute_categories",
                return_value={"items": payload["items"], "count": 1},
            ),
            patch.object(
                marketplace_mapping_routes,
                "_service_param_defs_payload",
                return_value=[],
            ),
        ):
            marketplace_mapping_routes._attr_bootstrap_cache["ts"] = 0.0
            marketplace_mapping_routes._attr_bootstrap_cache["payload"] = None
            response = self.client.get("/api/marketplaces/mapping/import/attributes/bootstrap")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["count"], 1)
        self.assertIn("items", body)

    def test_templates_editor_bootstrap_endpoint(self) -> None:
        templates_db = {
            "templates": {
                "tpl-1": {
                    "id": "tpl-1",
                    "category_id": "cat-1",
                    "name": "Template 1",
                }
            },
            "attributes": {"tpl-1": []},
        }
        path = [{"id": "cat-1", "name": "Категория"}]
        with (
            patch.object(templates_routes, "_get_catalog_nodes", return_value=path),
            patch.object(templates_routes, "_catalog_path", return_value=path),
            patch.object(
                templates_routes,
                "load_template_editor_payload",
                return_value={"template": templates_db["templates"]["tpl-1"], "attributes": [], "owner_category_id": "cat-1"},
            ),
            patch.object(templates_routes, "_ensure_default_attrs", side_effect=lambda attrs: attrs),
            patch.object(
                templates_routes,
                "_template_master_payload",
                return_value={"version": 2, "base_attributes": [], "category_attributes": [], "stats": {}, "sources": {}},
            ),
        ):
            response = self.client.get("/api/templates/editor-bootstrap/cat-1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["category"]["id"], "cat-1")
        self.assertIn("master", body)

    def test_catalog_products_page_data_endpoint(self) -> None:
        with (
            patch.object(catalog_routes, "_products_page_meta", return_value={"nodes": [], "groups": [], "templates": []}),
            patch.object(catalog_routes, "_ensure_catalog_product_page_summary", return_value=None),
            patch.object(catalog_routes, "_collect_subtree_ids", return_value=set()),
            patch.object(catalog_routes, "query_catalog_product_page_rows", return_value={"items": [], "total": 0}),
        ):
            response = self.client.get("/api/catalog/products-page-data")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("products", body)
        self.assertIn("page", body)
        self.assertIn("page_size", body)

    def test_catalog_products_counts_endpoint(self) -> None:
        with patch.object(catalog_routes, "load_category_product_counts", return_value={"cat-1": 3, "cat-2": 7}):
            response = self.client.get("/api/catalog/products/counts")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("counts", body)
        self.assertEqual(body["counts"]["cat-1"], 3)

    def test_info_model_draft_endpoint(self) -> None:
        with patch.object(
            info_models_routes.draft_service,
            "create_draft_from_sources",
            return_value={
                "ok": True,
                "template": {"id": "tpl-draft-vr", "category_id": "cat-vr", "name": "Draft: VR"},
                "info_model": {"status": "draft"},
                "candidates": [{"id": "cand-memory", "name": "Встроенная память"}],
            },
        ):
            response = self.client.post("/api/info-models/draft-from-sources", json={"category_id": "cat-vr", "sources": ["products"]})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["template"]["id"], "tpl-draft-vr")
        self.assertEqual(body["info_model"]["status"], "draft")

    def test_info_model_approve_endpoint(self) -> None:
        with patch.object(
            info_models_routes.draft_service,
            "approve_draft",
            return_value={
                "ok": True,
                "template": {"id": "tpl-draft-vr"},
                "info_model": {"status": "approved"},
                "attributes": [{"id": "attr-memory", "name": "Встроенная память"}],
            },
        ):
            response = self.client.post("/api/info-models/tpl-draft-vr/approve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["info_model"]["status"], "approved")
