import unittest

from fastapi.testclient import TestClient

from app.main import app


class HealthRouteTests(unittest.TestCase):
    def test_health_returns_ok(self) -> None:
        client = TestClient(app)
        response = client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})

    def test_storage_health_reports_s3_config_state(self) -> None:
        client = TestClient(app)
        response = client.get("/api/health/storage")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("ok", payload)
        self.assertIn("s3_enabled", payload)
