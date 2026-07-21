"""Unit tests for OTP generation, OTP verification, and OTP auth endpoints."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.routers.auth import send_otp, verify_otp_endpoint
from app.schemas import SendOtpRequest, VerifyOtpRequest
from app.services.auth import generate_otp, verify_otp


class TestOTPAuthentication(unittest.TestCase):

    def test_generate_otp(self):
        """Verify 6-digit numeric OTP generation."""
        otp = generate_otp(6)
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_verify_otp_valid(self):
        """Verify valid non-expired OTP matching."""
        user = MagicMock()
        user.otp_code = "482910"
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        self.assertTrue(verify_otp(user, "482910"))

    def test_verify_otp_invalid_code(self):
        """Verify mismatched OTP rejection."""
        user = MagicMock()
        user.otp_code = "482910"
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        self.assertFalse(verify_otp(user, "123456"))

    def test_verify_otp_expired(self):
        """Verify expired OTP rejection."""
        user = MagicMock()
        user.otp_code = "482910"
        user.otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        self.assertFalse(verify_otp(user, "482910"))

    def test_verify_otp_endpoint_success(self):
        """Verify verify_otp_endpoint marks user email verified."""
        user = MagicMock()
        user.id = "user_otp_1"
        user.email = "test@diva.ai"
        user.is_active = True
        user.is_deleted = False
        user.is_email_verified = False
        user.otp_code = "654321"
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        # UserOut.model_validate needs real field types, not MagicMocks
        user.display_name = "Test User"
        user.avatar_url = None
        user.generation_count = 0
        user.created_at = datetime.now(timezone.utc)

        db = MagicMock()
        db.scalars.return_value.first.return_value = user

        req = VerifyOtpRequest(email="test@diva.ai", otp="654321")
        response = verify_otp_endpoint(req, db=db)

        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.otp_code)
        self.assertIsNotNone(response.access_token)

    def test_send_otp_never_leaks_code(self):
        """A3 regression: OTP goes to email, never into the API response."""
        user = MagicMock()
        user.id = "user_otp_2"
        user.email = "test@diva.ai"

        db = MagicMock()
        db.scalars.return_value.first.return_value = user

        with patch("app.routers.auth.send_email") as mock_send:
            response = send_otp(SendOtpRequest(email="test@diva.ai"), db=db)

        # Code emailed…
        mock_send.assert_called_once()
        self.assertRegex(mock_send.call_args.args[2], r"\d{6}")
        # …but absent from the response
        self.assertNotRegex(response.message, r"\d{6}")


if __name__ == "__main__":
    unittest.main()
