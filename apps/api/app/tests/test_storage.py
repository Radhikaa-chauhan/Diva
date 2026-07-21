"""Unit tests for storage service covering S3, local storage, atomic writes, and security boundaries."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.storage import (
    MAX_FILE_SIZE_BYTES,
    _resolve_safe_path,
    delete_file,
    extract_s3_key,
    get_file_size,
    save_bytes,
    url_for,
)


class TestStorageService(unittest.TestCase):

    def test_path_traversal_prevention(self):
        """Verify path traversal attempts are blocked via relative_to."""
        valid_path = _resolve_safe_path("http://localhost:8000/storage/results/test.jpg")
        self.assertIsNotNone(valid_path)

        # Path traversal URL
        invalid_path = _resolve_safe_path("http://localhost:8000/storage/../../etc/passwd")
        self.assertIsNone(invalid_path)

        # Null or empty URL
        self.assertIsNone(_resolve_safe_path(""))
        self.assertIsNone(_resolve_safe_path(None))

    def test_extract_s3_key(self):
        """Verify robust S3 key extraction and unquoting."""
        url = "https://mybucket.s3.us-east-1.amazonaws.com/results/my%20file.jpg?AWSAccessKeyId=123"
        key = extract_s3_key(url)
        self.assertEqual(key, "results/my file.jpg")

        # Invalid URL format returns None
        self.assertIsNone(extract_s3_key("http://localhost:8000/storage/local.jpg"))
        self.assertIsNone(extract_s3_key(""))

    def test_max_file_size_limit(self):
        """Verify save_bytes rejects payload exceeding MAX_FILE_SIZE_BYTES."""
        huge_data = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        with self.assertRaises(ValueError) as ctx:
            save_bytes("results", "huge.jpg", huge_data)
        self.assertIn("exceeds maximum limit", str(ctx.exception))

    def test_empty_file_rejection(self):
        """Verify save_bytes rejects empty payload."""
        with self.assertRaises(ValueError) as ctx:
            save_bytes("results", "empty.jpg", b"")
        self.assertIn("Cannot save empty file data", str(ctx.exception))

    @patch("app.services.storage._get_s3_client")
    def test_mime_type_detection(self, mock_get_s3_client):
        """Verify dynamic MIME type resolution for S3 uploads."""
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test.png"

        # PNG detection
        save_bytes("results", "image.png", b"data")
        call_args = mock_s3.put_object.call_args[1]
        self.assertEqual(call_args["ContentType"], "image/png")

        # PDF detection
        save_bytes("results", "doc.pdf", b"data")
        call_args = mock_s3.put_object.call_args[1]
        self.assertEqual(call_args["ContentType"], "application/pdf")

    @patch("app.services.storage._get_s3_client")
    def test_s3_upload(self, mock_get_s3_client):
        """Verify successful upload to AWS S3."""
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/mybucket/results/123.jpg"

        url = save_bytes("results", "photo.jpg", b"image bytes")
        self.assertIn(".amazonaws.com/results/", url)
        self.assertNotIn("X-Amz", url)  # G9: no expiring presigned URL in the DB
        mock_s3.put_object.assert_called_once()

    @patch("app.services.storage._get_s3_client")
    def test_s3_fallback_to_local(self, mock_get_s3_client):
        """Verify graceful local storage fallback if S3 upload raises an error."""
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("S3 Service Unavailable")
        mock_get_s3_client.return_value = mock_s3

        data = b"fallback content"
        url = save_bytes("fallback_dir", "test.jpg", data)
        self.assertIn("/storage/fallback_dir/", url)

        # File is created locally
        size = get_file_size(url)
        self.assertEqual(size, len(data))

        # Cleanup
        delete_file(url)

    @patch("app.services.storage._get_s3_client")
    def test_s3_delete(self, mock_get_s3_client):
        """Verify deletion of files stored in AWS S3."""
        mock_s3 = MagicMock()
        mock_get_s3_client.return_value = mock_s3
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.aws_s3_bucket_name = "mybucket"
            
            s3_url = "https://mybucket.s3.us-east-1.amazonaws.com/results/photo.jpg"
            result = delete_file(s3_url)
            self.assertTrue(result)
            mock_s3.delete_object.assert_called_once_with(Bucket="mybucket", Key="results/photo.jpg")

    @patch("app.services.storage._get_s3_client", return_value=None)
    @patch("os.replace", side_effect=OSError("Disk write error"))
    def test_atomic_write_failure(self, mock_replace, mock_s3):
        """Verify atomic local write cleans up temp files and raises IOError on failure."""
        data = b"atomic failure test"
        with self.assertRaises(IOError) as ctx:
            save_bytes("fail_dir", "fail.jpg", data)
        self.assertIn("Failed to write file locally", str(ctx.exception))

    @patch("app.services.storage._get_s3_client")
    def test_url_generation(self, mock_get_s3_client):
        """Public prefixes get stable URLs; private keys get presigned; local gets /storage/."""
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/presigned_url"
        mock_get_s3_client.return_value = mock_s3

        # 1. Public feed content: stable object URL, never presigned (G9)
        result_url = url_for("results/test.jpg")
        self.assertIn(".amazonaws.com/results/test.jpg", result_url)
        self.assertNotIn("X-Amz", result_url)
        mock_s3.generate_presigned_url.assert_not_called()

        # 2. Private objects (selfies): presigned
        selfie_url = url_for("selfies/test.jpg", expiry_seconds=3600)
        self.assertEqual(selfie_url, "https://s3.amazonaws.com/presigned_url")
        self.assertEqual(
            mock_s3.generate_presigned_url.call_args.kwargs["Params"]["Key"],
            "selfies/test.jpg",
        )

        # 3. Local storage URL
        mock_get_s3_client.return_value = None
        local_url = url_for("results/test.jpg")
        self.assertIn("/storage/results/test.jpg", local_url)

    @patch("app.services.storage._get_s3_client", return_value=None)
    def test_atomic_local_save_and_delete(self, mock_s3):
        """Verify local file save executes atomically and file can be deleted."""
        data = b"test image content"
        url = save_bytes("test_dir", "test.jpg", data)
        self.assertIn("/storage/test_dir/", url)

        # Verify size
        size = get_file_size(url)
        self.assertEqual(size, len(data))

        # Delete file
        deleted = delete_file(url)
        self.assertTrue(deleted)
        self.assertEqual(get_file_size(url), 0)


if __name__ == "__main__":
    unittest.main()
