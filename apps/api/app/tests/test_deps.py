"""Unit tests for authentication and authorization dependencies in deps.py."""
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.deps import get_current_user, get_current_user_optional, require_verified_user


class TestDepsDependencies(unittest.TestCase):

    def test_get_current_user_no_credentials(self):
        """Verify 401 raises when no credentials provided."""
        db = MagicMock()
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=None, db=db)
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.deps.decode_token_payload")
    def test_get_current_user_valid(self, mock_decode):
        """Verify successful user authentication."""
        mock_decode.return_value = {"sub": "user_123", "token_version": 0}
        db = MagicMock()
        user = MagicMock()
        user.id = "user_123"
        user.is_active = True
        user.is_deleted = False
        user.token_version = 0
        db.get.return_value = user

        credentials = MagicMock()
        credentials.credentials = "valid_token"

        result = get_current_user(credentials=credentials, db=db)
        self.assertEqual(result, user)

    @patch("app.deps.decode_token_payload")
    def test_token_version_mismatch_revocation(self, mock_decode):
        """Verify token revocation on token_version mismatch."""
        mock_decode.return_value = {"sub": "user_123", "token_version": 0}
        db = MagicMock()
        user = MagicMock()
        user.id = "user_123"
        user.is_active = True
        user.is_deleted = False
        user.token_version = 1  # Incremented after logout
        db.get.return_value = user

        credentials = MagicMock()
        credentials.credentials = "old_token"

        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=credentials, db=db)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertIn("revoked", str(ctx.exception.detail).lower())

    @patch("app.deps.decode_token_payload")
    def test_soft_deleted_user_denied(self, mock_decode):
        """Verify soft deleted users cannot authenticate."""
        mock_decode.return_value = {"sub": "user_123", "token_version": 0}
        db = MagicMock()
        user = MagicMock()
        user.id = "user_123"
        user.is_active = True
        user.is_deleted = True  # Soft deleted
        user.token_version = 0
        db.get.return_value = user

        credentials = MagicMock()
        credentials.credentials = "valid_token"

        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=credentials, db=db)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_verified_user(self):
        """Verify email verification dependency."""
        verified_user = MagicMock()
        verified_user.is_email_verified = True
        self.assertEqual(require_verified_user(verified_user), verified_user)

        unverified_user = MagicMock()
        unverified_user.is_email_verified = False
        with self.assertRaises(HTTPException) as ctx:
            require_verified_user(unverified_user)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
