"""A4 regression: Google login without GOOGLE_CLIENT_ID must fail cleanly, not crash."""
import unittest
from unittest.mock import patch

from app.services import auth as auth_service
from app.services.auth import verify_social_token


class TestOAuth(unittest.TestCase):

    def test_google_without_client_id_returns_none(self):
        with patch.object(auth_service.settings, "google_client_id", None, create=True):
            result = verify_social_token("google", "a-plausible-looking-google-id-token")
        self.assertIsNone(result)

    def test_mock_token_rejected_in_production(self):
        with patch.object(auth_service.settings, "environment", "production"):
            result = verify_social_token("google", "mock:evil@example.com:Evil")
        self.assertIsNone(result)

    def test_mock_token_accepted_in_development(self):
        with patch.object(auth_service.settings, "environment", "development"):
            result = verify_social_token("google", "mock:dev@example.com:Dev User")
        self.assertEqual(result["email"], "dev@example.com")


if __name__ == "__main__":
    unittest.main()
