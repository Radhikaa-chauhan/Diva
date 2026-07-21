"""Unit tests for OTP generation, OTP verification, and OTP auth endpoints."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

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

        db = MagicMock()
        db.scalars.return_value.first.return_value = user

        req = VerifyOtpRequest(email="test@diva.ai", otp="654321")
        response = verify_otp_endpoint(req, db=db)

        self.assertTrue(user.is_email_verified)
        self.assertIsNone(user.otp_code)
        self.assertIsNotNone(response.access_token)


if __name__ == "__main__":
    unittest.main()
