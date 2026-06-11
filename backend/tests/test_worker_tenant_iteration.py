import os
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, os.path.abspath("backend"))

from app.core.control_plane import DEFAULT_ORGANIZATION_ID
from app.api.routes import connectors_status
from app.workers import tenant_iteration


class WorkerTenantIterationTests(unittest.TestCase):
    def test_explicit_organization_is_used_as_single_scope(self) -> None:
        self.assertEqual(tenant_iteration.active_worker_organization_ids("org_gsm_king"), ["org_gsm_king"])

    def test_active_worker_organization_ids_returns_active_tenants(self) -> None:
        with patch.object(
            tenant_iteration,
            "list_organizations_overview",
            return_value=[
                {"id": "org_default", "status": "active", "tenant_status": "active"},
                {"id": "org_gsm_king", "status": "active", "tenant_status": "active"},
                {"id": "org_pending", "status": "active", "tenant_status": "provisioning"},
                {"id": "org_deleted", "status": "deleted", "tenant_status": "active"},
            ],
        ):
            self.assertEqual(
                tenant_iteration.active_worker_organization_ids(),
                ["org_default", "org_gsm_king"],
            )

    def test_active_worker_organization_ids_falls_back_to_default(self) -> None:
        with patch.object(tenant_iteration, "list_organizations_overview", side_effect=RuntimeError("db down")):
            self.assertEqual(tenant_iteration.active_worker_organization_ids(), [DEFAULT_ORGANIZATION_ID])

    def test_connectors_scheduler_organization_ids_returns_active_tenants(self) -> None:
        with patch.object(
            connectors_status,
            "list_organizations_overview",
            return_value=[
                {"id": "org_default", "status": "active", "tenant_status": "active"},
                {"id": "org_device_mall", "status": "active", "tenant_status": "active"},
                {"id": "org_pending", "status": "active", "tenant_status": "provisioning"},
            ],
        ):
            self.assertEqual(
                connectors_status._active_scheduler_organization_ids(),
                ["org_default", "org_device_mall"],
            )


if __name__ == "__main__":
    unittest.main()
