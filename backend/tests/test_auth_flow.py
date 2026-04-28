import asyncio
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.core import auth as auth_core
from app.core import tenant_context as tenant_context_core
from app.api.routes import catalog as catalog_routes
from app.api.routes import attributes as attributes_routes
from app.api.routes import competitor_mapping as competitor_mapping_routes
from app.api.routes import connectors_status as connectors_status_routes
from app.api.routes import marketplace_mapping as marketplace_mapping_routes
from app.api.routes import platform as platform_routes
from app.api.routes import templates as templates_routes


class AuthFlowTests(unittest.TestCase):
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

        self.client = TestClient(app)

    def test_auth_session_is_public_and_unauthenticated_by_default(self) -> None:
        response = self.client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["authenticated"], False)
        self.assertIn("catalog", payload)
        self.assertIn("pages", payload["catalog"])
        self.assertIn("actions", payload["catalog"])

    def test_protected_auth_endpoint_requires_session(self) -> None:
        response = self.client.get("/api/auth/admin/bootstrap")

        self.assertEqual(response.status_code, 401)
        self.assertIn("AUTH_REQUIRED", response.text)

    def test_login_session_and_logout_flow(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")

        login_response = self.client.post(
            "/api/auth/login",
            json={"login": "owner", "password": "testpass123"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.json()["authenticated"], True)
        self.assertIn(auth_core.SESSION_COOKIE, login_response.cookies)

        session_response = self.client.get("/api/auth/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.json()["authenticated"], True)
        self.assertEqual(session_response.json()["user"]["login"], "owner")
        self.assertIn("organizations", session_response.json())
        self.assertIn("current_organization", session_response.json())
        self.assertIn("flags", session_response.json())
        self.assertIn("effective_access", session_response.json())

        logout_response = self.client.post("/api/auth/logout")
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"ok": True})

        session_after_logout = self.client.get("/api/auth/session")
        self.assertEqual(session_after_logout.status_code, 200)
        self.assertEqual(session_after_logout.json()["authenticated"], False)

    def test_owner_can_open_admin_bootstrap_after_login(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        response = self.client.get("/api/auth/admin/bootstrap")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertIn("roles", payload)
        self.assertIn("users", payload)
        self.assertIn("events", payload)

    def test_platform_organization_switch_updates_session_context(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        with (
            patch.object(auth_core, "can_access_organization", return_value=True),
            patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx),
        ):
            list_response = self.client.get("/api/platform/organizations")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()["organizations"]), 2)
            self.assertEqual(list_response.json()["current_organization"]["id"], "org_default")

            switch_response = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_beta"},
            )
            self.assertEqual(switch_response.status_code, 200)
            self.assertEqual(switch_response.json()["current_organization"]["id"], "org_beta")

            session_response = self.client.get("/api/auth/session")
            self.assertEqual(session_response.status_code, 200)
            self.assertEqual(session_response.json()["current_organization"]["id"], "org_beta")

    def test_platform_register_creates_session_payload(self) -> None:
        user = {
            "id": "user_new",
            "login": "owner@example.com",
            "email": "owner@example.com",
            "name": "Owner",
            "is_active": True,
            "role_ids": ["role_owner"],
            "pages": ["*"],
            "actions": ["*"],
        }
        organization = {
            "id": "org_new",
            "slug": "acme",
            "name": "Acme",
            "status": "provisioning",
            "membership_role": "org_owner",
        }

        with (
            patch.object(platform_routes, "find_user_by_login_or_email", return_value=None),
            patch.object(platform_routes, "ensure_user_account", return_value=user),
            patch.object(platform_routes, "create_organization_with_owner", return_value=organization),
            patch.object(platform_routes, "create_session", return_value="session-token"),
            patch.object(platform_routes, "load_auth_base_db", return_value={"users": {"user_new": user}, "roles": {}}),
            patch.object(platform_routes, "build_auth_context", return_value=auth_core.AuthContext(user, [], {"*"}, {"*"})),
            patch.object(
                platform_routes,
                "session_payload",
                return_value={
                    "authenticated": True,
                    "user": user,
                    "organizations": [organization],
                    "current_organization": organization,
                    "flags": {"is_developer": False},
                },
            ),
        ):
            response = self.client.post(
                "/api/platform/register",
                json={
                    "email": "owner@example.com",
                    "password": "secret123",
                    "name": "Owner",
                    "organization_name": "Acme",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_organization"]["id"], "org_new")
        self.assertIn(auth_core.SESSION_COOKIE, response.cookies)

    def test_platform_accept_invite_creates_user_when_missing(self) -> None:
        user = {
            "id": "user_invited",
            "login": "editor@example.com",
            "email": "editor@example.com",
            "name": "Editor",
            "is_active": True,
            "role_ids": ["role_viewer"],
            "pages": ["dashboard"],
            "actions": [],
        }
        organization = {
            "id": "org_new",
            "slug": "acme",
            "name": "Acme",
            "status": "active",
            "membership_role": "org_editor",
        }

        with (
            patch.object(platform_routes, "find_user_by_login_or_email", return_value=None),
            patch.object(platform_routes, "ensure_user_account", return_value=user),
            patch.object(platform_routes, "accept_organization_invite", return_value={"organization": organization}),
            patch.object(platform_routes, "create_session", return_value="session-token"),
            patch.object(platform_routes, "load_auth_base_db", return_value={"users": {"user_invited": user}, "roles": {}}),
            patch.object(platform_routes, "build_auth_context", return_value=auth_core.AuthContext(user, [], {"dashboard"}, set())),
            patch.object(
                platform_routes,
                "session_payload",
                return_value={
                    "authenticated": True,
                    "user": user,
                    "organizations": [organization],
                    "current_organization": organization,
                    "flags": {"is_developer": False},
                },
            ),
        ):
            response = self.client.post(
                "/api/platform/invites/accept",
                json={
                    "token": "invite-token",
                    "email": "editor@example.com",
                    "name": "Editor",
                    "password": "secret123",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_organization"]["id"], "org_new")
        self.assertIn(auth_core.SESSION_COOKIE, response.cookies)

    def test_current_organization_status_endpoint_returns_status_payload(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        status_payload = {
            "organization": {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "provisioning",
                "created_at": None,
                "updated_at": None,
            },
            "tenant_registry": {
                "organization_id": "org_default",
                "db_host": "",
                "db_port": 5432,
                "db_name": "tenant_default",
                "db_user": "",
                "db_secret_ref": "tenant_registry/org_default",
                "status": "provisioning",
                "schema_version": None,
                "created_at": None,
                "updated_at": None,
            },
            "latest_job": {
                "id": "tenant_job_1",
                "organization_id": "org_default",
                "status": "pending",
                "attempt": 0,
                "error": None,
                "created_at": None,
                "updated_at": None,
            },
        }

        with patch.object(platform_routes, "get_organization_provisioning_status", return_value=status_payload):
            response = self.client.get("/api/platform/organizations/current/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["organization"]["status"], "provisioning")
        self.assertEqual(body["latest_job"]["status"], "pending")

    def test_workspace_bootstrap_returns_organizations_members_and_invites(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        session_ctx = {
            "platform_roles": [],
            "organizations": [
                {
                    "id": "org_default",
                    "slug": "default",
                    "name": "Default organization",
                    "status": "active",
                    "membership_role": "org_owner",
                }
            ],
            "current_organization": {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            "flags": {"is_developer": False},
        }
        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
                "tenant_status": "provisioning",
                "member_count": 1,
                "pending_invite_count": 1,
            }
        ]
        members = [
            {
                "id": "member_1",
                "organization_id": "org_default",
                "platform_user_id": "user_owner",
                "org_role_code": "org_owner",
                "status": "active",
                "email": "owner@example.com",
                "name": "Owner",
                "user_status": "active",
                "last_login_at": None,
            }
        ]
        invites = [
            {
                "id": "invite_1",
                "organization_id": "org_default",
                "email": "editor@example.com",
                "org_role_code": "org_editor",
                "status": "pending",
                "expires_at": None,
                "accepted_at": None,
                "created_at": None,
            }
        ]

        with (
            patch.object(platform_routes, "session_payload", return_value=session_ctx),
            patch.object(platform_routes, "can_access_organization", return_value=True),
            patch.object(platform_routes, "list_organizations_overview", return_value=organizations),
            patch.object(platform_routes, "list_organization_members", return_value=members),
            patch.object(platform_routes, "list_organization_invites", return_value=invites),
            patch.object(platform_routes, "tenant_context_payload", return_value={"organization_id": "org_default"}),
        ):
            response = self.client.get("/api/platform/workspace/bootstrap?organization_id=org_default")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["selected_organization"]["id"], "org_default")
        self.assertEqual(len(body["members"]), 1)
        self.assertEqual(len(body["invites"]), 1)

    def test_current_tenant_context_endpoint_returns_resolved_context(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        tenant_payload = {
            "resolved": True,
            "tenant": {
                "organization_id": "org_default",
                "organization_slug": "default",
                "organization_name": "Default organization",
                "organization_status": "provisioning",
                "tenant_status": "provisioning",
                "tenant_db_name": "tenant_default",
                "tenant_db_host": "",
                "schema_version": None,
                "ready": False,
                "source": "session",
            },
        }

        with patch.object(platform_routes, "tenant_context_payload", return_value=tenant_payload):
            response = self.client.get("/api/platform/tenant/current")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["ok"], True)
        self.assertEqual(body["resolved"], True)
        self.assertEqual(body["tenant"]["organization_id"], "org_default")

    def test_connectors_status_is_isolated_by_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        per_org_store: dict[str, dict[str, object]] = {}

        def fake_load_connectors_state_doc(organization_id=None):
            org_id = str(organization_id or "").strip() or "org_default"
            return deepcopy(per_org_store.get(org_id, {"version": 1, "updated_at": None, "providers": {}}))

        def fake_save_connectors_state_doc(doc, organization_id=None):
            org_id = str(organization_id or "").strip() or "org_default"
            per_org_store[org_id] = deepcopy(doc)

        def fake_request_org_id(request):
            return request.headers.get("x-test-org", "org_default")

        with (
            patch.object(connectors_status_routes, "load_connectors_state_doc", side_effect=fake_load_connectors_state_doc),
            patch.object(connectors_status_routes, "save_connectors_state_doc", side_effect=fake_save_connectors_state_doc),
            patch.object(connectors_status_routes, "_request_organization_id", side_effect=fake_request_org_id),
        ):
            alpha_create = self.client.post(
                "/api/connectors/status/import-stores",
                headers={"x-test-org": "org_alpha"},
                json={
                    "provider": "yandex_market",
                    "title": "Alpha Store",
                    "business_id": "1001",
                    "token": "alpha-token",
                    "auth_mode": "api-key",
                    "enabled": True,
                },
            )
            self.assertEqual(alpha_create.status_code, 200)
            alpha_payload = alpha_create.json()
            alpha_stores = alpha_payload["providers"][0]["import_stores"]
            self.assertEqual(len(alpha_stores), 1)
            self.assertEqual(alpha_stores[0]["business_id"], "1001")

            beta_state = self.client.get(
                "/api/connectors/status",
                headers={"x-test-org": "org_beta"},
            )
            self.assertEqual(beta_state.status_code, 200)
            beta_providers = {row["code"]: row for row in beta_state.json()["providers"]}
            self.assertEqual(beta_providers["yandex_market"]["import_stores"], [])

            beta_create = self.client.post(
                "/api/connectors/status/import-stores",
                headers={"x-test-org": "org_beta"},
                json={
                    "provider": "yandex_market",
                    "title": "Beta Store",
                    "business_id": "2002",
                    "token": "beta-token",
                    "auth_mode": "api-key",
                    "enabled": True,
                },
            )
            self.assertEqual(beta_create.status_code, 200)

            alpha_state = self.client.get(
                "/api/connectors/status",
                headers={"x-test-org": "org_alpha"},
            )
            alpha_providers = {row["code"]: row for row in alpha_state.json()["providers"]}
            self.assertEqual(len(alpha_providers["yandex_market"]["import_stores"]), 1)
            self.assertEqual(alpha_providers["yandex_market"]["import_stores"][0]["business_id"], "1001")

            beta_state_after = self.client.get(
                "/api/connectors/status",
                headers={"x-test-org": "org_beta"},
            )
            beta_providers_after = {row["code"]: row for row in beta_state_after.json()["providers"]}
            self.assertEqual(len(beta_providers_after["yandex_market"]["import_stores"]), 1)
            self.assertEqual(beta_providers_after["yandex_market"]["import_stores"][0]["business_id"], "2002")

    def test_marketplace_category_mappings_are_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_mappings: dict[str, dict[str, dict[str, str]]] = {}

        def fake_load_category_mappings():
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            return deepcopy(per_org_mappings.get(org_id, {}))

        def fake_save_category_mappings(items):
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            per_org_mappings[org_id] = deepcopy(items if isinstance(items, dict) else {})

        marketplace_mapping_routes._import_categories_cache.clear()
        marketplace_mapping_routes._attr_categories_cache.clear()
        marketplace_mapping_routes._attr_details_cache.clear()
        marketplace_mapping_routes._attr_bootstrap_cache.clear()
        marketplace_mapping_routes._value_details_cache.clear()

        with (
            patch.object(auth_core, "can_access_organization", return_value=True),
            patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx),
            patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status),
            patch.object(marketplace_mapping_routes, "load_category_mappings", side_effect=fake_load_category_mappings),
            patch.object(marketplace_mapping_routes, "save_category_mappings", side_effect=fake_save_category_mappings),
            patch.object(
                marketplace_mapping_routes,
                "_load_catalog_nodes",
                return_value=[{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 0}],
            ),
            patch.object(
                marketplace_mapping_routes,
                "_load_provider_categories",
                return_value=[
                    {"id": "ym1", "name": "YM 1", "path": "YM 1", "is_leaf": True},
                    {"id": "ym2", "name": "YM 2", "path": "YM 2", "is_leaf": True},
                ],
            ),
            patch.object(marketplace_mapping_routes, "_build_competitor_states", return_value={}),
            patch.object(marketplace_mapping_routes, "_persistent_cache_read", return_value=None),
            patch.object(marketplace_mapping_routes, "_persistent_cache_write", return_value=None),
            patch.object(marketplace_mapping_routes, "_persistent_cache_clear", return_value=None),
            patch.object(marketplace_mapping_routes, "_persistent_attr_details_cache_clear_all", return_value=None),
        ):
            default_link = self.client.post(
                "/api/marketplaces/mapping/import/categories/link",
                json={
                    "catalog_category_id": "cat1",
                    "provider": "yandex_market",
                    "provider_category_id": "ym1",
                },
            )
            self.assertEqual(default_link.status_code, 200)
            self.assertEqual(default_link.json()["mappings"]["cat1"]["yandex_market"], "ym1")

            default_categories = self.client.get("/api/marketplaces/mapping/import/categories")
            self.assertEqual(default_categories.status_code, 200)
            self.assertEqual(default_categories.json()["mappings"]["cat1"]["yandex_market"], "ym1")

            switch_to_beta = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_beta"},
            )
            self.assertEqual(switch_to_beta.status_code, 200)
            self.assertEqual(switch_to_beta.json()["current_organization"]["id"], "org_beta")

            beta_before = self.client.get("/api/marketplaces/mapping/import/categories")
            self.assertEqual(beta_before.status_code, 200)
            self.assertEqual(beta_before.json()["mappings"], {})

            beta_link = self.client.post(
                "/api/marketplaces/mapping/import/categories/link",
                json={
                    "catalog_category_id": "cat1",
                    "provider": "yandex_market",
                    "provider_category_id": "ym2",
                },
            )
            self.assertEqual(beta_link.status_code, 200)
            self.assertEqual(beta_link.json()["mappings"]["cat1"]["yandex_market"], "ym2")

            switch_to_default = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_default"},
            )
            self.assertEqual(switch_to_default.status_code, 200)
            self.assertEqual(switch_to_default.json()["current_organization"]["id"], "org_default")

            default_after = self.client.get("/api/marketplaces/mapping/import/categories")
            self.assertEqual(default_after.status_code, 200)
            self.assertEqual(default_after.json()["mappings"]["cat1"]["yandex_market"], "ym1")

    def test_marketplace_attribute_mappings_are_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_attr_docs: dict[str, dict[str, object]] = {}
        per_org_value_docs: dict[str, dict[str, object]] = {}

        def fake_load_attribute_mapping_doc():
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            return deepcopy(per_org_attr_docs.get(org_id, {"version": 1, "items": {}}))

        def fake_save_attribute_mapping_doc(doc):
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            per_org_attr_docs[org_id] = deepcopy(doc if isinstance(doc, dict) else {"version": 1, "items": {}})

        def fake_load_attribute_value_refs_doc():
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            return deepcopy(per_org_value_docs.get(org_id, {"version": 2, "updated_at": None, "items": {}}))

        def fake_save_attribute_value_refs_doc(doc):
            org_id = marketplace_mapping_routes.current_tenant_organization_id()
            per_org_value_docs[org_id] = deepcopy(doc if isinstance(doc, dict) else {"version": 2, "updated_at": None, "items": {}})

        marketplace_mapping_routes._import_categories_cache.clear()
        marketplace_mapping_routes._attr_categories_cache.clear()
        marketplace_mapping_routes._attr_details_cache.clear()
        marketplace_mapping_routes._attr_bootstrap_cache.clear()
        marketplace_mapping_routes._value_details_cache.clear()

        with ExitStack() as stack:
            stack.enter_context(patch.object(auth_core, "can_access_organization", return_value=True))
            stack.enter_context(patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx))
            stack.enter_context(patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_category_mappings", return_value={"cat1": {"yandex_market": "ym1"}}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_attribute_mapping_doc", side_effect=fake_load_attribute_mapping_doc))
            stack.enter_context(patch.object(marketplace_mapping_routes, "save_attribute_mapping_doc", side_effect=fake_save_attribute_mapping_doc))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_attribute_value_refs_doc", side_effect=fake_load_attribute_value_refs_doc))
            stack.enter_context(patch.object(marketplace_mapping_routes, "save_attribute_value_refs_doc", side_effect=fake_save_attribute_value_refs_doc))
            stack.enter_context(
                patch.object(
                    marketplace_mapping_routes,
                    "_load_catalog_nodes",
                    return_value=[{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 0}],
                )
            )
            stack.enter_context(patch.object(marketplace_mapping_routes, "_load_yandex_params", return_value=[{"id": "param_a", "name": "Param A"}, {"id": "param_b", "name": "Param B"}]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_has_yandex_params_cached", return_value=True))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_provider_category_name", return_value="YM category"))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_load_ozon_params", return_value=[]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_has_ozon_params_cached", return_value=False))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_catalog_attr_options_for_category", return_value=[]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_migrate_mapping_documents_to_canonical_names", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_templates_db", return_value={"category_to_templates": {}, "templates": {}}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_upsert_template_from_attr_mapping", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_upsert_attr_values_dictionary_for_category", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_record_feedback_from_rows", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_persistent_cache_read", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_persistent_cache_write", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_persistent_cache_clear", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_persistent_attr_details_cache_clear_all", return_value=None))
            default_save = self.client.put(
                "/api/marketplaces/mapping/import/attributes/cat1",
                json={
                    "rows": [
                        {
                            "id": "row_a",
                            "catalog_name": "Attr A",
                            "group": "О товаре",
                            "confirmed": True,
                            "provider_map": {
                                "yandex_market": {
                                    "id": "param_a",
                                    "name": "Param A",
                                    "kind": "ENUM",
                                    "values": ["One"],
                                    "required": True,
                                    "export": True,
                                }
                            },
                        }
                    ],
                    "apply_to_category_ids": [],
                },
            )
            self.assertEqual(default_save.status_code, 200)
            self.assertEqual(default_save.json()["rows_count"], 1)

            default_details = self.client.get("/api/marketplaces/mapping/import/attributes/cat1")
            self.assertEqual(default_details.status_code, 200)
            self.assertEqual(default_details.json()["rows"][0]["catalog_name"], "Attr A")

            switch_to_beta = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_beta"},
            )
            self.assertEqual(switch_to_beta.status_code, 200)

            beta_before = self.client.get("/api/marketplaces/mapping/import/attributes/cat1")
            self.assertEqual(beta_before.status_code, 200)
            self.assertEqual(beta_before.json()["rows"], [])

            beta_save = self.client.put(
                "/api/marketplaces/mapping/import/attributes/cat1",
                json={
                    "rows": [
                        {
                            "id": "row_b",
                            "catalog_name": "Attr B",
                            "group": "О товаре",
                            "confirmed": True,
                            "provider_map": {
                                "yandex_market": {
                                    "id": "param_b",
                                    "name": "Param B",
                                    "kind": "ENUM",
                                    "values": ["Two"],
                                    "required": False,
                                    "export": True,
                                }
                            },
                        }
                    ],
                    "apply_to_category_ids": [],
                },
            )
            self.assertEqual(beta_save.status_code, 200)

            beta_details = self.client.get("/api/marketplaces/mapping/import/attributes/cat1")
            self.assertEqual(beta_details.status_code, 200)
            self.assertEqual(beta_details.json()["rows"][0]["catalog_name"], "Attr B")

            switch_to_default = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_default"},
            )
            self.assertEqual(switch_to_default.status_code, 200)

            default_after = self.client.get("/api/marketplaces/mapping/import/attributes/cat1")
            self.assertEqual(default_after.status_code, 200)
            self.assertEqual(default_after.json()["rows"][0]["catalog_name"], "Attr A")

    def test_competitor_mapping_is_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_competitor_db: dict[str, dict[str, object]] = {}

        def fake_load_competitor_mapping_db():
            org_id = tenant_context_core.current_tenant_organization_id()
            return deepcopy(per_org_competitor_db.get(org_id, {"version": 2, "categories": {}, "templates": {}}))

        def fake_save_competitor_mapping_db(db):
            org_id = tenant_context_core.current_tenant_organization_id()
            per_org_competitor_db[org_id] = deepcopy(db if isinstance(db, dict) else {"version": 2, "categories": {}, "templates": {}})

        competitor_mapping_routes._bootstrap_cache.clear()

        with ExitStack() as stack:
            stack.enter_context(patch.object(auth_core, "can_access_organization", return_value=True))
            stack.enter_context(patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx))
            stack.enter_context(patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status))
            stack.enter_context(patch.object(competitor_mapping_routes, "load_competitor_mapping_db", side_effect=fake_load_competitor_mapping_db))
            stack.enter_context(patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=fake_save_competitor_mapping_db))
            stack.enter_context(patch.object(competitor_mapping_routes, "_resolve_template_for_category", return_value=("tpl1", "cat1")))
            stack.enter_context(patch.object(competitor_mapping_routes, "load_templates_db", return_value={"templates": {"tpl1": {"id": "tpl1", "name": "Template 1", "category_id": "cat1"}}, "attributes": {}}))
            stack.enter_context(patch.object(competitor_mapping_routes, "_invalidate_marketplace_mapping_caches", return_value=None))

            default_save = self.client.put(
                "/api/competitor-mapping/category/cat1",
                json={
                    "priority_site": "restore",
                    "links": {
                        "restore": "https://re-store.ru/test-product",
                        "store77": "https://store77.net/test-product",
                    },
                    "mapping_by_site": {
                        "restore": {"attr_a": "spec a"},
                        "store77": {"attr_a": "spec b"},
                    },
                },
            )
            self.assertEqual(default_save.status_code, 200)
            self.assertTrue(default_save.json()["configured"])

            default_get = self.client.get("/api/competitor-mapping/category/cat1")
            self.assertEqual(default_get.status_code, 200)
            self.assertEqual(default_get.json()["data"]["mapping_by_site"]["restore"]["attr_a"], "spec a")

            switch_to_beta = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_beta"},
            )
            self.assertEqual(switch_to_beta.status_code, 200)

            beta_get_before = self.client.get("/api/competitor-mapping/category/cat1")
            self.assertEqual(beta_get_before.status_code, 200)
            self.assertEqual(beta_get_before.json()["data"]["mapping_by_site"]["restore"], {})
            self.assertEqual(beta_get_before.json()["data"]["mapping_by_site"]["store77"], {})

            beta_save = self.client.put(
                "/api/competitor-mapping/category/cat1",
                json={
                    "priority_site": "store77",
                    "links": {
                        "restore": "https://re-store.ru/beta-product",
                        "store77": "https://store77.net/beta-product",
                    },
                    "mapping_by_site": {
                        "restore": {"attr_b": "beta restore"},
                        "store77": {"attr_b": "beta store"},
                    },
                },
            )
            self.assertEqual(beta_save.status_code, 200)
            self.assertTrue(beta_save.json()["configured"])

            beta_get = self.client.get("/api/competitor-mapping/category/cat1")
            self.assertEqual(beta_get.status_code, 200)
            self.assertEqual(beta_get.json()["data"]["mapping_by_site"]["restore"]["attr_b"], "beta restore")

            switch_to_default = self.client.post(
                "/api/platform/organizations/switch",
                json={"organization_id": "org_default"},
            )
            self.assertEqual(switch_to_default.status_code, 200)

            default_after = self.client.get("/api/competitor-mapping/category/cat1")
            self.assertEqual(default_after.status_code, 200)
            self.assertEqual(default_after.json()["data"]["mapping_by_site"]["restore"]["attr_a"], "spec a")

    def test_catalog_products_page_marketplace_status_is_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_status_rows: dict[str, list[dict[str, object]]] = {}
        per_org_page_rows: dict[str, list[dict[str, object]]] = {}

        def fake_save_product_marketplace_status(rows, organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            per_org_status_rows[org_id] = deepcopy(rows if isinstance(rows, list) else [])

        def fake_load_product_marketplace_status_map(organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            rows = per_org_status_rows.get(org_id, [])
            payload = {}
            for row in rows:
                product_id = str((row or {}).get("product_id") or "").strip()
                if not product_id:
                    continue
                payload[product_id] = {
                    "yandex_market": {
                        "present": bool((row or {}).get("yandex_present") or False),
                        "status": str((row or {}).get("yandex_status") or "Нет данных"),
                    },
                    "ozon": {
                        "present": bool((row or {}).get("ozon_present") or False),
                        "status": str((row or {}).get("ozon_status") or "Нет данных"),
                    },
                }
            return payload

        def fake_save_catalog_product_page_rows(rows, organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            per_org_page_rows[org_id] = deepcopy(rows if isinstance(rows, list) else [])

        def fake_query_catalog_product_page_rows(**kwargs):
            org_id = str(kwargs.get("organization_id") or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            rows = per_org_page_rows.get(org_id, [])
            items = []
            for row in rows:
                items.append(
                    {
                        "id": str(row.get("product_id") or row.get("id") or ""),
                        "product_id": str(row.get("product_id") or row.get("id") or ""),
                        "title": str(row.get("title") or ""),
                        "name": str(row.get("title") or ""),
                        "category_id": str(row.get("category_id") or ""),
                        "category_path": str(row.get("category_path") or ""),
                        "sku_pim": str(row.get("sku_pim") or ""),
                        "sku_gt": str(row.get("sku_gt") or ""),
                        "group_id": str(row.get("group_id") or ""),
                        "group_name": str(row.get("group_name") or ""),
                        "effective_template_id": str(row.get("template_id") or ""),
                        "effective_template_name": str(row.get("template_name") or ""),
                        "effective_template_source_category_id": str(row.get("template_source_category_id") or ""),
                        "marketplace_statuses": {
                            "yandex_market": {
                                "present": bool(row.get("yandex_present") or False),
                                "status": str(row.get("yandex_status") or "Нет данных"),
                            },
                            "ozon": {
                                "present": bool(row.get("ozon_present") or False),
                                "status": str(row.get("ozon_status") or "Нет данных"),
                            },
                        },
                        "preview_url": str(row.get("preview_url") or ""),
                        "exports_enabled": row.get("exports_enabled") if isinstance(row.get("exports_enabled"), dict) else {},
                    }
                )
            return {"items": items, "total": len(items)}

        def fake_products_page_meta():
            templates_db = fake_load_templates_db()
            templates_map = templates_db.get("templates") if isinstance(templates_db.get("templates"), dict) else {}
            template_items = []
            for tid, row in templates_map.items():
                if not isinstance(row, dict):
                    continue
                template_items.append(
                    {
                        "id": str(row.get("id") or tid),
                        "category_id": str(row.get("category_id") or ""),
                        "name": str(row.get("name") or ""),
                    }
                )
            return {
                "nodes": [{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 1}],
                "groups": [],
                "templates": template_items,
                "templates_db": templates_db,
            }

        def fake_marketplace_statuses_for_product(product, ctx):
            org_id = catalog_routes.current_tenant_organization_id()
            if org_id == "org_beta":
                return {
                    "yandex_market": {"present": False, "status": "Нет данных"},
                    "ozon": {"present": True, "status": "На модерации"},
                }
            return {
                "yandex_market": {"present": True, "status": "Опубликован"},
                "ozon": {"present": False, "status": "Нет данных"},
            }

        catalog_routes._products_page_cache.clear()
        catalog_routes._products_page_result_cache.clear()
        catalog_routes._template_resolution_state.clear()
        catalog_routes._marketplace_summary_state.clear()
        catalog_routes._product_page_summary_state.clear()

        with ExitStack() as stack:
            stack.enter_context(patch.object(auth_core, "can_access_organization", return_value=True))
            stack.enter_context(patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx))
            stack.enter_context(patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status))
            stack.enter_context(
                patch.object(
                    catalog_routes,
                    "_products_page_meta",
                    return_value={
                        "nodes": [{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 1}],
                        "groups": [],
                        "templates": [],
                        "templates_db": {"category_to_templates": {}, "templates": {}},
                    },
                )
            )
            stack.enter_context(
                patch.object(
                    catalog_routes,
                    "_load_products",
                    return_value=[
                        {
                            "id": "prod1",
                            "title": "Console Alpha",
                            "name": "Console Alpha",
                            "category_id": "cat1",
                            "sku_pim": "SKU-PIM-1",
                            "sku_gt": "1001",
                            "group_id": "",
                            "preview_url": "",
                            "exports_enabled": {},
                        }
                    ],
                )
            )
            stack.enter_context(patch.object(catalog_routes, "_ensure_category_template_resolution", return_value={}))
            stack.enter_context(patch.object(catalog_routes, "_build_marketplace_status_context", return_value={}))
            stack.enter_context(patch.object(catalog_routes, "save_product_marketplace_status", side_effect=fake_save_product_marketplace_status))
            stack.enter_context(patch.object(catalog_routes, "load_product_marketplace_status_map", side_effect=fake_load_product_marketplace_status_map))
            stack.enter_context(patch.object(catalog_routes, "save_catalog_product_page_rows", side_effect=fake_save_catalog_product_page_rows))
            stack.enter_context(patch.object(catalog_routes, "query_catalog_product_page_rows", side_effect=fake_query_catalog_product_page_rows))
            stack.enter_context(patch.object(catalog_routes, "_marketplace_statuses_for_product", side_effect=fake_marketplace_statuses_for_product))

            default_response = self.client.get("/api/catalog/products-page-data", params={"refresh": True})
            self.assertEqual(default_response.status_code, 200)
            default_product = default_response.json()["products"][0]
            self.assertEqual(default_product["marketplace_statuses"]["yandex_market"]["status"], "Опубликован")
            self.assertFalse(default_product["marketplace_statuses"]["ozon"]["present"])

            switch_to_beta = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_beta"})
            self.assertEqual(switch_to_beta.status_code, 200)

            beta_response = self.client.get("/api/catalog/products-page-data", params={"refresh": True})
            self.assertEqual(beta_response.status_code, 200)
            beta_product = beta_response.json()["products"][0]
            self.assertEqual(beta_product["marketplace_statuses"]["yandex_market"]["status"], "Нет данных")
            self.assertTrue(beta_product["marketplace_statuses"]["ozon"]["present"])

            switch_to_default = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_default"})
            self.assertEqual(switch_to_default.status_code, 200)

            default_after = self.client.get("/api/catalog/products-page-data")
            self.assertEqual(default_after.status_code, 200)
            default_after_product = default_after.json()["products"][0]
            self.assertEqual(default_after_product["marketplace_statuses"]["yandex_market"]["status"], "Опубликован")
            self.assertFalse(default_after_product["marketplace_statuses"]["ozon"]["present"])

    def test_templates_and_category_resolution_are_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_templates: dict[str, dict[str, object]] = {
            "org_default": {
                "version": 2,
                "templates": {
                    "tpl_default": {"id": "tpl_default", "name": "Template Default", "category_id": "cat1", "created_at": "", "updated_at": ""},
                },
                "attributes": {
                    "tpl_default": [{"id": "a1", "name": "Brand", "code": "brand", "type": "text", "required": True, "scope": "common", "options": {}, "position": 0}],
                },
                "category_to_template": {"cat1": "tpl_default"},
                "category_to_templates": {"cat1": ["tpl_default"]},
            },
            "org_beta": {
                "version": 2,
                "templates": {
                    "tpl_beta": {"id": "tpl_beta", "name": "Template Beta", "category_id": "cat1", "created_at": "", "updated_at": ""},
                },
                "attributes": {
                    "tpl_beta": [{"id": "a2", "name": "Model", "code": "model", "type": "text", "required": False, "scope": "common", "options": {}, "position": 0}],
                },
                "category_to_template": {"cat1": "tpl_beta"},
                "category_to_templates": {"cat1": ["tpl_beta"]},
            },
        }
        per_org_resolution: dict[str, dict[str, dict[str, str]]] = {}
        per_org_page_rows: dict[str, list[dict[str, object]]] = {}

        def fake_load_templates_db():
            org_id = tenant_context_core.current_tenant_organization_id()
            return deepcopy(per_org_templates.get(org_id, {"version": 2, "templates": {}, "attributes": {}, "category_to_template": {}, "category_to_templates": {}}))

        def fake_save_category_template_resolution(rows, organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            per_org_resolution[org_id] = {
                str(row.get("category_id") or "").strip(): {
                    "template_id": str(row.get("template_id") or "").strip(),
                    "template_name": str(row.get("template_name") or "").strip(),
                    "source_category_id": str(row.get("source_category_id") or "").strip(),
                }
                for row in (rows or [])
                if str(row.get("category_id") or "").strip()
            }

        def fake_load_category_template_resolution_map(organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            return deepcopy(per_org_resolution.get(org_id, {}))

        def fake_save_catalog_product_page_rows(rows, organization_id=None):
            org_id = str(organization_id or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            per_org_page_rows[org_id] = deepcopy(rows if isinstance(rows, list) else [])

        def fake_query_catalog_product_page_rows(**kwargs):
            org_id = str(kwargs.get("organization_id") or catalog_routes.current_tenant_organization_id()).strip() or "org_default"
            rows = per_org_page_rows.get(org_id, [])
            items = []
            for row in rows:
                items.append(
                    {
                        "id": str(row.get("product_id") or row.get("id") or ""),
                        "product_id": str(row.get("product_id") or row.get("id") or ""),
                        "title": str(row.get("title") or ""),
                        "name": str(row.get("title") or ""),
                        "category_id": str(row.get("category_id") or ""),
                        "category_path": str(row.get("category_path") or ""),
                        "sku_pim": str(row.get("sku_pim") or ""),
                        "sku_gt": str(row.get("sku_gt") or ""),
                        "group_id": str(row.get("group_id") or ""),
                        "group_name": str(row.get("group_name") or ""),
                        "effective_template_id": str(row.get("template_id") or ""),
                        "effective_template_name": str(row.get("template_name") or ""),
                        "effective_template_source_category_id": str(row.get("template_source_category_id") or ""),
                        "marketplace_statuses": {
                            "yandex_market": {"present": False, "status": "Нет данных"},
                            "ozon": {"present": False, "status": "Нет данных"},
                        },
                        "preview_url": str(row.get("preview_url") or ""),
                        "exports_enabled": row.get("exports_enabled") if isinstance(row.get("exports_enabled"), dict) else {},
                    }
                )
            return {"items": items, "total": len(items)}

        def fake_products_page_meta():
            templates_db = fake_load_templates_db()
            templates_map = templates_db.get("templates") if isinstance(templates_db.get("templates"), dict) else {}
            template_items = []
            for tid, row in templates_map.items():
                if not isinstance(row, dict):
                    continue
                template_items.append(
                    {
                        "id": str(row.get("id") or tid),
                        "category_id": str(row.get("category_id") or ""),
                        "name": str(row.get("name") or ""),
                    }
                )
            return {
                "nodes": [{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 1}],
                "groups": [],
                "templates": template_items,
                "templates_db": templates_db,
            }

        catalog_routes._products_page_cache.clear()
        catalog_routes._products_page_result_cache.clear()
        catalog_routes._template_resolution_state.clear()
        catalog_routes._marketplace_summary_state.clear()
        catalog_routes._product_page_summary_state.clear()

        with ExitStack() as stack:
            stack.enter_context(patch.object(auth_core, "can_access_organization", return_value=True))
            stack.enter_context(patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx))
            stack.enter_context(patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status))
            stack.enter_context(patch.object(templates_routes, "load_templates_db", side_effect=fake_load_templates_db))
            stack.enter_context(patch.object(templates_routes, "_ensure_default_attrs", side_effect=lambda attrs: attrs))
            stack.enter_context(patch.object(templates_routes, "load_category_mappings", return_value={}))
            stack.enter_context(patch.object(catalog_routes, "load_templates_db", side_effect=fake_load_templates_db))
            stack.enter_context(patch.object(catalog_routes, "save_category_template_resolution", side_effect=fake_save_category_template_resolution))
            stack.enter_context(patch.object(catalog_routes, "load_category_template_resolution_map", side_effect=fake_load_category_template_resolution_map))
            stack.enter_context(patch.object(catalog_routes, "save_catalog_product_page_rows", side_effect=fake_save_catalog_product_page_rows))
            stack.enter_context(patch.object(catalog_routes, "query_catalog_product_page_rows", side_effect=fake_query_catalog_product_page_rows))
            stack.enter_context(patch.object(catalog_routes, "_ensure_marketplace_status_summary", return_value={}))
            stack.enter_context(patch.object(catalog_routes, "_products_page_meta", side_effect=fake_products_page_meta))
            stack.enter_context(
                patch.object(
                    catalog_routes,
                    "_load_products",
                    return_value=[
                        {
                            "id": "prod1",
                            "title": "Console Alpha",
                            "name": "Console Alpha",
                            "category_id": "cat1",
                            "sku_pim": "SKU-PIM-1",
                            "sku_gt": "1001",
                            "group_id": "",
                            "preview_url": "",
                            "exports_enabled": {},
                        }
                    ],
                )
            )

            default_templates = self.client.get("/api/templates/by-category/cat1")
            self.assertEqual(default_templates.status_code, 200)
            self.assertEqual(default_templates.json()["template"]["id"], "tpl_default")

            default_page = self.client.get("/api/catalog/products-page-data", params={"refresh": True})
            self.assertEqual(default_page.status_code, 200)
            self.assertEqual(default_page.json()["products"][0]["effective_template_id"], "tpl_default")

            switch_to_beta = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_beta"})
            self.assertEqual(switch_to_beta.status_code, 200)

            beta_templates = self.client.get("/api/templates/by-category/cat1")
            self.assertEqual(beta_templates.status_code, 200)
            self.assertEqual(beta_templates.json()["template"]["id"], "tpl_beta")

            beta_page = self.client.get("/api/catalog/products-page-data", params={"refresh": True})
            self.assertEqual(beta_page.status_code, 200)
            self.assertEqual(beta_page.json()["products"][0]["effective_template_id"], "tpl_beta")

            switch_to_default = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_default"})
            self.assertEqual(switch_to_default.status_code, 200)

            default_again = self.client.get("/api/catalog/products-page-data")
            self.assertEqual(default_again.status_code, 200)
            self.assertEqual(default_again.json()["products"][0]["effective_template_id"], "tpl_default")

    def test_global_attributes_are_isolated_by_current_organization(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        organizations = [
            {
                "id": "org_default",
                "slug": "default",
                "name": "Default organization",
                "status": "active",
                "membership_role": "org_owner",
            },
            {
                "id": "org_beta",
                "slug": "beta",
                "name": "Beta",
                "status": "active",
                "membership_role": "org_editor",
            },
        ]

        def fake_session_ctx(user, roles, current_organization_id=None):
            current = next((row for row in organizations if row["id"] == current_organization_id), None) or organizations[0]
            return {
                "platform_roles": [],
                "organizations": organizations,
                "current_organization": current,
                "flags": {"is_developer": False},
            }

        def fake_org_status(organization_id):
            target = next((row for row in organizations if row["id"] == organization_id), organizations[0])
            return {
                "organization": {
                    "id": target["id"],
                    "slug": target["slug"],
                    "name": target["name"],
                    "status": "active",
                    "created_at": None,
                    "updated_at": None,
                },
                "tenant_registry": {
                    "organization_id": target["id"],
                    "db_host": "",
                    "db_port": 5432,
                    "db_name": f"tenant_{target['slug']}",
                    "db_user": "",
                    "db_secret_ref": f"tenant_registry/{target['id']}",
                    "status": "active",
                    "schema_version": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "latest_job": {
                    "id": f"tenant_job_{target['id']}",
                    "organization_id": target["id"],
                    "status": "done",
                    "attempt": 1,
                    "error": None,
                    "created_at": None,
                    "updated_at": None,
                },
            }

        per_org_dicts: dict[str, dict[str, object]] = {}

        def fake_load_dictionaries_db():
            org_id = tenant_context_core.current_tenant_organization_id()
            return deepcopy(per_org_dicts.get(org_id, {"version": 2, "items": []}))

        def fake_save_dictionaries_db(db):
            org_id = tenant_context_core.current_tenant_organization_id()
            per_org_dicts[org_id] = deepcopy(db if isinstance(db, dict) else {"version": 2, "items": []})

        def fake_ensure_global_attribute(title: str, type_: str, code=None, scope: str = "both"):
            org_id = tenant_context_core.current_tenant_organization_id()
            db = deepcopy(per_org_dicts.get(org_id, {"version": 2, "items": []}))
            items = db.get("items") if isinstance(db.get("items"), list) else []
            final_code = str(code or title).strip().lower().replace(" ", "_")
            dict_id = f"dict_{final_code}"
            existing = next((row for row in items if isinstance(row, dict) and str(row.get("id") or "") == dict_id), None)
            if not existing:
                existing = {
                    "id": dict_id,
                    "title": title,
                    "code": final_code,
                    "attr_id": f"attr_{org_id}_{final_code}",
                    "type": type_,
                    "scope": scope,
                    "dict_id": dict_id,
                    "items": [],
                    "aliases": {},
                    "meta": {},
                    "created_at": "",
                    "updated_at": "",
                }
                items.append(existing)
                db["items"] = items
                per_org_dicts[org_id] = deepcopy(db)
            return {
                "id": existing["attr_id"],
                "title": existing["title"],
                "code": existing["code"],
                "type": existing["type"],
                "scope": existing["scope"],
                "dict_id": existing["id"],
            }

        with ExitStack() as stack:
            stack.enter_context(patch.object(auth_core, "can_access_organization", return_value=True))
            stack.enter_context(patch.object(auth_core, "load_user_session_context", side_effect=fake_session_ctx))
            stack.enter_context(patch.object(tenant_context_core, "get_organization_provisioning_status", side_effect=fake_org_status))
            stack.enter_context(patch.object(attributes_routes, "load_dictionaries_db", side_effect=fake_load_dictionaries_db))
            stack.enter_context(patch.object(attributes_routes, "save_dictionaries_db", side_effect=fake_save_dictionaries_db))
            stack.enter_context(patch.object(attributes_routes, "ensure_global_attribute", side_effect=fake_ensure_global_attribute))

            default_ensure = self.client.post(
                "/api/attributes/ensure",
                json={"title": "Brand", "type": "text", "code": "brand", "scope": "feature"},
            )
            self.assertEqual(default_ensure.status_code, 200)
            self.assertEqual(default_ensure.json()["attribute"]["id"], "attr_org_default_brand")

            default_list = self.client.get("/api/attributes")
            self.assertEqual(default_list.status_code, 200)
            self.assertEqual(len(default_list.json()["items"]), 1)
            self.assertEqual(default_list.json()["items"][0]["id"], "attr_org_default_brand")

            switch_to_beta = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_beta"})
            self.assertEqual(switch_to_beta.status_code, 200)

            beta_before = self.client.get("/api/attributes")
            self.assertEqual(beta_before.status_code, 200)
            self.assertEqual(beta_before.json()["items"], [])

            beta_ensure = self.client.post(
                "/api/attributes/ensure",
                json={"title": "Brand", "type": "text", "code": "brand", "scope": "feature"},
            )
            self.assertEqual(beta_ensure.status_code, 200)
            self.assertEqual(beta_ensure.json()["attribute"]["id"], "attr_org_beta_brand")

            beta_list = self.client.get("/api/attributes")
            self.assertEqual(beta_list.status_code, 200)
            self.assertEqual(len(beta_list.json()["items"]), 1)
            self.assertEqual(beta_list.json()["items"][0]["id"], "attr_org_beta_brand")

            switch_to_default = self.client.post("/api/platform/organizations/switch", json={"organization_id": "org_default"})
            self.assertEqual(switch_to_default.status_code, 200)

            default_after = self.client.get("/api/attributes")
            self.assertEqual(default_after.status_code, 200)
            self.assertEqual(len(default_after.json()["items"]), 1)
            self.assertEqual(default_after.json()["items"][0]["id"], "attr_org_default_brand")

    def test_attribute_ai_match_falls_back_quickly_when_ollama_hangs(self) -> None:
        async def slow_ollama(*args, **kwargs):
            await asyncio.sleep(0.3)
            return None

        marketplace_mapping_routes._import_categories_cache.clear()
        marketplace_mapping_routes._attr_categories_cache.clear()
        marketplace_mapping_routes._attr_details_cache.clear()
        marketplace_mapping_routes._attr_bootstrap_cache.clear()
        marketplace_mapping_routes._value_details_cache.clear()

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(
                    marketplace_mapping_routes,
                    "_load_catalog_nodes",
                    return_value=[{"id": "cat1", "parent_id": None, "name": "Consoles", "position": 0, "template_id": None, "products_count": 0}],
                )
            )
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_category_mappings", return_value={"cat1": {"yandex_market": "ym1"}}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_load_yandex_params", return_value=[{"id": "param_a", "name": "Param A"}]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_catalog_attr_options_for_category", return_value=[]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_service_param_defs_payload", return_value=[]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_attribute_mapping_doc", return_value={"version": 1, "items": {}}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "save_attribute_mapping_doc", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_dictionaries_db", return_value={"version": 2, "items": []}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "load_templates_db", return_value={"category_to_templates": {}, "templates": {}}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_load_attr_feedback_doc", return_value={}))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_prune_rows_for_current_provider_params", return_value=[]))
            stack.enter_context(
                patch.object(
                    marketplace_mapping_routes,
                    "_catalog_target_rows",
                    return_value=[{"id": "row_1", "catalog_name": "Param A", "group": "Base", "provider_map": {}, "confirmed": False}],
                )
            )
            stack.enter_context(patch.object(marketplace_mapping_routes, "_merge_existing_into_target_rows", side_effect=lambda target_rows, _existing_rows: target_rows))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_apply_group_locks", side_effect=lambda rows: rows))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_deterministic_ai_rows", return_value=[]))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_upsert_template_from_attr_mapping", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_upsert_attr_values_dictionary_for_category", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_persistent_cache_clear", return_value=None))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_ollama_suggest_rows", side_effect=slow_ollama))
            stack.enter_context(patch.object(marketplace_mapping_routes, "_AI_MATCH_OLLAMA_TIMEOUT_SECONDS", 0.05))

            started = time.monotonic()
            response = asyncio.run(marketplace_mapping_routes.mapping_attribute_ai_match("cat1", marketplace_mapping_routes.AiMatchReq(apply=True)))
            elapsed = time.monotonic() - started

        self.assertEqual(response["engine"], "fallback")
        self.assertLess(elapsed, 0.25)

    def test_competitor_discovery_sources_include_restore_and_store77(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        response = self.client.get("/api/competitor-mapping/discovery/sources")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        source_ids = [item["id"] for item in payload["sources"]]
        self.assertEqual(source_ids, ["restore", "store77"])

    def test_competitor_discovery_run_creates_moderation_candidates(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {"version": 2, "categories": {}, "templates": {}}
        saved_docs: list[dict] = []

        async def fake_discover(product, source):
            return [
                {
                    "url": f"https://{source['domain']}/product/{product['id']}",
                    "title": f"{product['title']} competitor",
                    "confidence_score": 0.91,
                    "confidence_reasons": ["title совпал", "source разрешен"],
                }
            ]

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", return_value=store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=lambda doc: saved_docs.append(deepcopy(doc))),
            patch.object(
                competitor_mapping_routes,
                "_discovery_products",
                return_value=[{"id": "product_1", "title": "iPhone 16 Pro", "sku_gt": "10001", "category_id": "phones"}],
                create=True,
            ),
            patch.object(competitor_mapping_routes, "_discover_product_candidates_for_source", side_effect=fake_discover, create=True),
        ):
            response = self.client.post(
                "/api/competitor-mapping/discovery/run",
                json={"product_ids": ["product_1"], "sources": ["restore", "store77"]},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["created_count"], 2)
        self.assertEqual(payload["run"]["status"], "completed")
        self.assertEqual(len(saved_docs[-1]["discovery"]["candidates"]), 2)

    def test_competitor_discovery_run_marks_missing_review_candidates_stale(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    "cand_old": {
                        "id": "cand_old",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/catalog/bad/",
                        "status": "needs_review",
                    }
                },
                "links": {},
                "runs": {},
            },
        }
        saved_docs: list[dict] = []

        def save_doc(doc):
            saved_docs.append(deepcopy(doc))

        async def fake_discover(product, source):
            return []

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", side_effect=lambda: store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=save_doc),
            patch.object(
                competitor_mapping_routes,
                "_discovery_products",
                return_value=[{"id": "product_1", "title": "iPhone 16 Pro", "sku_gt": "10001", "category_id": "phones"}],
                create=True,
            ),
            patch.object(competitor_mapping_routes, "_discover_product_candidates_for_source", side_effect=fake_discover, create=True),
        ):
            response = self.client.post(
                "/api/competitor-mapping/discovery/run",
                json={"product_ids": ["product_1"], "sources": ["restore"]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_docs[-1]["discovery"]["candidates"]["cand_old"]["status"], "stale")

    def test_competitor_candidate_moderation_approves_and_rejects_candidates(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    "cand_restore": {
                        "id": "cand_restore",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/product/iphone",
                        "status": "needs_review",
                        "confidence_score": 0.94,
                    },
                    "cand_store77": {
                        "id": "cand_store77",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/product/iphone",
                        "status": "needs_review",
                        "confidence_score": 0.82,
                    },
                },
                "links": {},
                "runs": {},
            },
        }
        saved_docs: list[dict] = []

        def save_doc(doc):
            next_doc = deepcopy(doc)
            store.clear()
            store.update(next_doc)
            saved_docs.append(deepcopy(next_doc))

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", side_effect=lambda: store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=save_doc),
        ):
            approve = self.client.post(
                "/api/competitor-mapping/discovery/candidates/cand_restore/moderate",
                json={"action": "approve"},
            )
            reject = self.client.post(
                "/api/competitor-mapping/discovery/candidates/cand_store77/moderate",
                json={"action": "reject", "reason": "Не тот товар"},
            )

        self.assertEqual(approve.status_code, 200)
        self.assertEqual(reject.status_code, 200)
        discovery = saved_docs[-1]["discovery"]
        self.assertEqual(discovery["candidates"]["cand_restore"]["status"], "approved")
        self.assertEqual(discovery["candidates"]["cand_store77"]["status"], "rejected")
        self.assertEqual(discovery["links"]["product_1:restore"]["candidate_id"], "cand_restore")
        self.assertEqual(discovery["links"]["product_1:restore"]["url"], "https://re-store.ru/product/iphone")

    def test_competitor_product_discovery_endpoint_returns_candidates_and_links(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    "cand_restore": {
                        "id": "cand_restore",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/product/iphone",
                        "status": "approved",
                        "confidence_score": 0.94,
                    },
                    "cand_stale": {
                        "id": "cand_stale",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/product/stale",
                        "status": "stale",
                        "confidence_score": 0.42,
                    },
                    "cand_other": {
                        "id": "cand_other",
                        "product_id": "product_2",
                        "source_id": "restore",
                        "url": "https://re-store.ru/product/other",
                        "status": "needs_review",
                        "confidence_score": 0.51,
                    },
                },
                "links": {
                    "product_1:restore": {
                        "candidate_id": "cand_restore",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/product/iphone",
                        "status": "approved",
                    }
                },
                "runs": {},
            },
        }

        with patch.object(competitor_mapping_routes, "load_competitor_mapping_db", return_value=store):
            response = self.client.get("/api/competitor-mapping/discovery/products/product_1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["product_id"], "product_1")
        self.assertEqual(payload["counts"]["total"], 2)
        self.assertEqual(payload["counts"]["approved"], 1)
        self.assertEqual(payload["counts"]["stale"], 1)
        self.assertEqual({item["id"] for item in payload["items"]}, {"cand_restore", "cand_stale"})
        self.assertEqual(payload["confirmed_links"][0]["candidate_id"], "cand_restore")

    def test_competitor_category_discovery_endpoint_summarizes_sources(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    "cand_restore": {
                        "id": "cand_restore",
                        "product_id": "product_1",
                        "source_id": "restore",
                        "url": "https://re-store.ru/catalog/apple/iphone/product-1/",
                        "title": "iPhone competitor",
                        "status": "needs_review",
                        "confidence_score": 0.91,
                    },
                    "cand_other_category": {
                        "id": "cand_other_category",
                        "product_id": "product_2",
                        "source_id": "restore",
                        "url": "https://re-store.ru/catalog/other/product-2/",
                        "status": "needs_review",
                        "confidence_score": 0.51,
                    },
                },
                "links": {
                    "product_1:store77": {
                        "id": "product_1:store77",
                        "product_id": "product_1",
                        "source_id": "store77",
                        "url": "https://store77.net/apple-iphone-16-pro/",
                        "status": "confirmed",
                    }
                },
                "runs": {},
            },
        }

        with (
            patch.object(
                competitor_mapping_routes,
                "_catalog_nodes",
                return_value=[
                    {"id": "phones", "parent_id": None, "name": "Смартфоны"},
                    {"id": "iphone", "parent_id": "phones", "name": "iPhone"},
                ],
            ),
            patch.object(
                competitor_mapping_routes,
                "query_products_full",
                return_value=[{"id": "product_1", "title": "iPhone 16 Pro", "category_id": "iphone"}],
            ),
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", return_value=store),
        ):
            response = self.client.get("/api/competitor-mapping/discovery/categories/phones")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["category"]["id"], "phones")
        self.assertEqual(payload["category"]["products_count"], 1)
        by_source = {item["id"]: item for item in payload["sources"]}
        self.assertEqual(by_source["restore"]["candidates_count"], 1)
        self.assertEqual(by_source["restore"]["needs_review_count"], 1)
        self.assertIn("catalog / apple / iphone", by_source["restore"]["suggestions"][0]["label"])
        self.assertEqual(by_source["store77"]["confirmed_count"], 1)
        self.assertEqual(by_source["store77"]["suggestions"][0]["type"], "observed")

    def test_restore_search_html_candidates_extract_product_links(self) -> None:
        html = r'''
          <script>
          window.__payload = {\"name\":\"Apple iPhone 16 256GB, White\",\"price\":\"89990\",\"brand\":\"Apple\",\"skuCode\":\"10116256WHTn\",\"link\":\"/catalog/10116256WHTN/\"};
          </script>
        '''
        product = {"id": "product_1", "title": "Apple iPhone 16", "sku_gt": "10116256WHTN"}

        candidates = competitor_mapping_routes._extract_restore_search_candidates(html, product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://re-store.ru/catalog/10116256WHTN/")
        self.assertEqual(candidates[0]["title"], "Apple iPhone 16 256GB, White")
        self.assertEqual(candidates[0]["sku"], "10116256WHTn")
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.8)

    def test_restore_search_html_candidates_reject_brand_mismatch(self) -> None:
        html = r'''
          <script>
          window.__payload = {\"name\":\"Смартфон Xiaomi 15 12/512 ГБ Зеленый\",\"price\":\"79990\",\"brand\":\"Xiaomi\",\"skuCode\":\"61306\",\"link\":\"/catalog/61306/\"};
          </script>
        '''
        product = {"id": "product_1", "title": "Смартфон Apple iPhone 17 Pro", "sku_gt": "52460"}

        candidates = competitor_mapping_routes._extract_restore_search_candidates(html, product)

        self.assertEqual(candidates, [])

    def test_restore_search_html_candidates_reject_same_brand_wrong_generation(self) -> None:
        html = r'''
          <script>
          window.__payload = {\"name\":\"Apple iPhone 16 Pro 256GB eSIM Silver\",\"price\":\"99990\",\"brand\":\"Apple\",\"skuCode\":\"10116256WHTn\",\"link\":\"/catalog/10116256WHTN/\"};
          </script>
        '''
        product = {"id": "product_1", "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)", "sku_gt": "52460"}

        candidates = competitor_mapping_routes._extract_restore_search_candidates(html, product)

        self.assertEqual(candidates, [])

    def test_restore_search_html_candidates_require_close_variant_match(self) -> None:
        html = r'''
          <script>
          window.__payload = {\"name\":\"Apple iPhone 17 Pro 256GB eSIM Silver\",\"price\":\"129990\",\"brand\":\"Apple\",\"skuCode\":\"AIPH17P256SIL\",\"link\":\"/catalog/AIPH17P256SIL/\"};
          </script>
        '''
        product = {"id": "product_1", "title": "Смартфон Apple iPhone 17 Pro 256Gb eSIM Silver (Global)", "sku_gt": "52460"}

        candidates = competitor_mapping_routes._extract_restore_search_candidates(html, product)

        self.assertEqual(len(candidates), 1)
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.8)
        self.assertIn("обязательные токены совпали", candidates[0]["confidence_reasons"])

    def test_competitor_discovery_background_run_is_queued_and_pollable(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {"version": 2, "categories": {}, "templates": {}}

        def save_doc(doc):
            next_doc = deepcopy(doc)
            store.clear()
            store.update(next_doc)

        launched: list[tuple[str, str | None]] = []

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", side_effect=lambda: store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=save_doc),
            patch.object(
                competitor_mapping_routes,
                "_start_discovery_worker_process",
                side_effect=lambda run_id, organization_id: launched.append((run_id, organization_id)),
            ),
            patch.object(competitor_mapping_routes, "_discovery_products", side_effect=AssertionError("background run must not execute inline"), create=True),
        ):
            response = self.client.post(
                "/api/competitor-mapping/discovery/run",
                json={"background": True, "sources": ["restore", "store77"], "limit": 50},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["ok"], True)
            self.assertEqual(payload["run"]["status"], "queued")
            run_id = payload["run"]["id"]
            self.assertEqual(launched, [(run_id, "org_default")])

            status = self.client.get(f"/api/competitor-mapping/discovery/runs/{run_id}")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["run"]["id"], run_id)
        self.assertEqual(status.json()["run"]["status"], "queued")

    def test_store77_search_html_candidates_extract_product_links(self) -> None:
        html = """
          <a class="product-card" href="/catalog/smartfony/apple-iphone-16-128gb-black/">
            Apple iPhone 16 128GB Black
          </a>
        """
        product = {"id": "product_1", "title": "Apple iPhone 16", "sku_gt": "10001"}

        candidates = competitor_mapping_routes._extract_store77_search_candidates(html, product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://store77.net/catalog/smartfony/apple-iphone-16-128gb-black/")
        self.assertEqual(candidates[0]["title"], "Apple iPhone 16 128GB Black")
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.6)

    def test_competitor_query_terms_prioritize_title_over_internal_sku(self) -> None:
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium (Global)",
            "sku_gt": "50046",
            "sku_pim": "113",
        }

        terms = competitor_mapping_routes._query_terms_for_product(product)

        self.assertIn("Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium", terms[0])
        self.assertNotEqual(terms[0], "50046")
        self.assertIn("50046", terms)

    def test_store77_search_html_candidates_extract_real_section_links(self) -> None:
        html = """
          <a class="product-card" href="/apple_iphone_16_pro_2/">
            Телефон Apple iPhone 16 Pro 128Gb eSim (Natural Titanium)
          </a>
        """
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb eSIM Natural Titanium (Global)",
            "sku_gt": "50046",
        }

        candidates = competitor_mapping_routes._extract_store77_search_candidates(html, product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["url"], "https://store77.net/apple_iphone_16_pro_2/")
        self.assertIn("Natural Titanium", candidates[0]["title"])

    def test_store77_category_urls_are_derived_from_iphone_title(self) -> None:
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium (Global)",
        }

        urls = competitor_mapping_routes._store77_category_urls_for_product(product)

        self.assertEqual(
            urls[:2],
            [
                "https://store77.net/apple_iphone_16_pro_2/",
                "https://store77.net/apple_iphone_16_pro/",
            ],
        )

    def test_store77_seed_candidate_builds_exact_iphone_product_url(self) -> None:
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium (Global)",
            "sku_gt": "50046",
        }

        candidates = competitor_mapping_routes._store77_seed_candidates_for_product(product)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]["url"],
            "https://store77.net/apple_iphone_16_pro_2/telefon_apple_iphone_16_pro_128gb_nano_sim_esim_natural_titanium/",
        )
        self.assertGreaterEqual(candidates[0]["confidence_score"], 0.9)

    def test_sim_profile_conflict_blocks_esim_only_candidate_for_nano_esim_product(self) -> None:
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium (Global)",
            "sku_gt": "50046",
        }

        score, reasons = competitor_mapping_routes._confidence_for_candidate(
            product,
            "Телефон Apple iPhone 16 Pro 128Gb eSim (Natural Titanium)",
            "",
        )

        self.assertEqual(score, 0.0)
        self.assertIn("конфликт SIM", reasons[0])

    def test_store77_seed_candidate_preserves_nano_esim_slug(self) -> None:
        product = {
            "id": "product_113",
            "title": "Смартфон Apple iPhone 16 Pro 128Gb nano SIM+eSIM Natural Titanium (Global)",
            "sku_gt": "50046",
        }

        candidates = competitor_mapping_routes._store77_seed_candidates_for_product(product)

        self.assertEqual(len(candidates), 1)
        self.assertIn("nano_sim_esim", candidates[0]["url"])
        self.assertIn("nano SIM+eSIM", candidates[0]["title"])

    def test_approving_candidate_rejects_sibling_variants(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        candidate_id = "cand_keep"
        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    candidate_id: {
                        "id": candidate_id,
                        "product_id": "product_113",
                        "source_id": "store77",
                        "url": "https://store77.net/apple_iphone_16_pro_2/keep/",
                        "status": "needs_review",
                        "match_group_key": "iphone_16_pro|128gb|natural_titanium",
                    },
                    "cand_sibling": {
                        "id": "cand_sibling",
                        "product_id": "product_113",
                        "source_id": "store77",
                        "url": "https://store77.net/apple_iphone_16_pro_2/sibling/",
                        "status": "needs_review",
                        "match_group_key": "iphone_16_pro|128gb|natural_titanium",
                    },
                    "cand_other": {
                        "id": "cand_other",
                        "product_id": "product_113",
                        "source_id": "store77",
                        "url": "https://store77.net/apple_iphone_16_pro_2/other/",
                        "status": "needs_review",
                        "match_group_key": "iphone_16_pro|256gb|natural_titanium",
                    },
                },
                "links": {},
                "runs": {},
            },
        }
        saved_docs: list[dict] = []

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", return_value=store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=lambda doc: saved_docs.append(deepcopy(doc))),
        ):
            response = self.client.post(
                f"/api/competitor-mapping/discovery/candidates/{candidate_id}/moderate",
                json={"action": "approve"},
            )

        self.assertEqual(response.status_code, 200)
        candidates = saved_docs[-1]["discovery"]["candidates"]
        self.assertEqual(candidates[candidate_id]["status"], "approved")
        self.assertEqual(candidates["cand_sibling"]["status"], "rejected")
        self.assertEqual(candidates["cand_sibling"]["rejection_reason"], "sibling_not_selected")
        self.assertEqual(candidates["cand_other"]["status"], "needs_review")

    def test_manual_competitor_link_confirms_link_and_rejects_pending_source_candidates(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        store = {
            "version": 2,
            "categories": {},
            "templates": {},
            "discovery": {
                "candidates": {
                    "cand_pending": {
                        "id": "cand_pending",
                        "product_id": "product_113",
                        "source_id": "store77",
                        "url": "https://store77.net/apple_iphone_16_pro_2/wrong/",
                        "status": "needs_review",
                    }
                },
                "links": {},
                "runs": {},
            },
        }
        saved_docs: list[dict] = []

        with (
            patch.object(competitor_mapping_routes, "load_competitor_mapping_db", return_value=store),
            patch.object(competitor_mapping_routes, "save_competitor_mapping_db", side_effect=lambda doc: saved_docs.append(deepcopy(doc))),
        ):
            response = self.client.post(
                "/api/competitor-mapping/discovery/products/product_113/links",
                json={
                    "source_id": "store77",
                    "url": "https://store77.net/apple_iphone_16_pro_2/manual/",
                },
            )

        self.assertEqual(response.status_code, 200)
        discovery = saved_docs[-1]["discovery"]
        self.assertEqual(discovery["links"]["product_113:store77"]["status"], "confirmed")
        self.assertEqual(discovery["links"]["product_113:store77"]["source"], "manual")
        self.assertEqual(discovery["candidates"]["cand_pending"]["status"], "rejected")
        self.assertEqual(discovery["candidates"]["cand_pending"]["rejection_reason"], "manual_link_selected")

    def test_competitor_discovery_unknown_background_run_keeps_polling(self) -> None:
        auth_core.ensure_owner_account("owner", "testpass123", name="Owner")
        self.client.post("/api/auth/login", json={"login": "owner", "password": "testpass123"})

        with patch.object(
            competitor_mapping_routes,
            "load_competitor_mapping_db",
            return_value={"version": 2, "categories": {}, "templates": {}, "discovery": {"runs": {}, "candidates": {}, "links": {}}},
        ):
            response = self.client.get("/api/competitor-mapping/discovery/runs/run_missing_worker_state")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["id"], "run_missing_worker_state")
        self.assertEqual(response.json()["run"]["status"], "running")
