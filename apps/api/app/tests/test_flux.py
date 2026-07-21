"""Tests for the generation adapter: selfie must reach the provider,
failures must propagate in prod, mock only in dev with the flag on."""
import asyncio
import io
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from app.services import flux
from app.services.flux import GenerationError, generate


def _tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(buf, format="JPEG")
    return buf.getvalue()


class TestGenerationAdapter(unittest.TestCase):

    def setUp(self):
        self.selfie = _tiny_jpeg()

    def test_selfie_bytes_reach_provider(self):
        """G1 regression: the selfie must be passed as the img2img input."""
        fake_client = MagicMock()
        fake_client.image_to_image.return_value = Image.new("RGB", (64, 64), "green")

        with patch.object(flux, "_get_hf_client", return_value=fake_client), \
             patch.object(flux.settings, "huggingface_api_key", "hf_test"):
            result = asyncio.run(generate(self.selfie, "editorial style"))

        kwargs = fake_client.image_to_image.call_args.kwargs
        self.assertEqual(kwargs["image"], self.selfie)
        self.assertEqual(kwargs["prompt"], "editorial style")
        self.assertEqual(result.provider_used, "huggingface")

    def test_prod_failure_propagates_no_silent_mock(self):
        """G3 regression: provider failure in prod = GenerationError, not sepia."""
        fake_client = MagicMock()
        fake_client.image_to_image.side_effect = RuntimeError("provider down")

        with patch.object(flux, "_get_hf_client", return_value=fake_client), \
             patch.object(flux.settings, "huggingface_api_key", "hf_test"), \
             patch.object(flux.settings, "environment", "production"), \
             patch.object(flux.settings, "allow_mock_fallback", False):
            with self.assertRaises(GenerationError):
                asyncio.run(generate(self.selfie, "editorial style"))

    def test_dev_mock_fallback_when_enabled(self):
        fake_client = MagicMock()
        fake_client.image_to_image.side_effect = RuntimeError("provider down")

        with patch.object(flux, "_get_hf_client", return_value=fake_client), \
             patch.object(flux.settings, "huggingface_api_key", "hf_test"), \
             patch.object(flux.settings, "environment", "development"), \
             patch.object(flux.settings, "allow_mock_fallback", True):
            result = asyncio.run(generate(self.selfie, "editorial style"))

        self.assertEqual(result.provider_used, "mock")
        self.assertTrue(result.image_bytes)

    def test_no_key_no_mock_raises(self):
        with patch.object(flux.settings, "huggingface_api_key", None), \
             patch.object(flux.settings, "allow_mock_fallback", False):
            with self.assertRaises(GenerationError):
                asyncio.run(generate(self.selfie, "editorial style"))


if __name__ == "__main__":
    unittest.main()
