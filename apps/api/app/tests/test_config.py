"""Unit tests for configuration loading and validation."""
import unittest
from unittest.mock import patch

from app.config import Settings, _sanitize_db_url, get_settings


class TestConfigValidation(unittest.TestCase):

    def test_sanitize_db_url(self):
        """Verify DB password masking in URL sanitizer."""
        url_with_pass = "postgresql://postgres:secretpassword123@localhost:5432/diva"
        sanitized = _sanitize_db_url(url_with_pass)
        self.assertNotIn("secretpassword123", sanitized)
        self.assertIn("postgres:***@", sanitized)

    def test_allowed_origins_list(self):
        """Verify parsing of single and multi-origin CORS strings."""
        settings = Settings(allowed_origin="http://localhost:3000, https://diva.com")
        self.assertEqual(settings.allowed_origins_list, ["http://localhost:3000", "https://diva.com"])

    def test_validation_max_generation_attempts(self):
        """Verify validation of max_generation_attempts."""
        with patch.dict("os.environ", {"MAX_GENERATION_ATTEMPTS": "0"}):
            get_settings.cache_clear()
            with self.assertRaises(ValueError):
                get_settings()
            get_settings.cache_clear()

    def test_validation_huggingface_model_format(self):
        """Verify huggingface_model format validation."""
        with patch.dict("os.environ", {"HUGGINGFACE_MODEL": "invalid_model_without_slash"}):
            get_settings.cache_clear()
            with self.assertRaises(ValueError):
                get_settings()
            get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
