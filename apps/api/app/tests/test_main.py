"""Unit tests for main FastAPI application initialization and routes."""
import unittest
from fastapi.testclient import TestClient

from app.main import app


class TestMainApp(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        """Verify health check endpoint returns 200 OK."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_app_title_and_version(self):
        """Verify FastAPI app title and version."""
        self.assertEqual(app.title, "Diva API")
        self.assertEqual(app.version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
