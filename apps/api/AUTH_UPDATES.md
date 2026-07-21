# Authentication System Enhancements — Documentation

## Overview

The authentication module (`app.routers.auth`) in Diva API has been updated to support production-grade security features and improved user onboarding:

1. **Email Verification**: Enables account recovery and verifies email ownership.
2. **Login Rate Limiting**: Protects against brute-force password guessing attacks.
3. **Password Reset Flow**: Allows self-serve password resets via secure time-limited tokens.
4. **Social OAuth Login**: Supports Google (and third-party OAuth provider) single sign-on.

---

## 1. Summary of Changes

| Component | File | Description |
| :--- | :--- | :--- |
| **Config** | [`app/config.py`](file:///c:/Projects/Diva/apps/api/app/config.py) | Added settings for rate limit thresholds and token expiration durations. |
| **Rate Limiter** | [`app/services/rate_limiter.py`](file:///c:/Projects/Diva/apps/api/app/services/rate_limiter.py) | Created in-memory sliding window rate-limiter dependency (`SlidingWindowRateLimiter`). |
| **Auth Service** | [`app/services/auth.py`](file:///c:/Projects/Diva/apps/api/app/services/auth.py) | Added JWT token creation/decoding functions for email verification and password resets, as well as social token verification helpers. |
| **Schemas** | [`app/schemas.py`](file:///c:/Projects/Diva/apps/api/app/schemas.py) | Added `is_email_verified` field to `UserOut` and created input models for verify email, forgot password, reset password, and social login. |
| **Router** | [`app/routers/auth.py`](file:///c:/Projects/Diva/apps/api/app/routers/auth.py) | Implemented new endpoints for verify-email, resend-verification, forgot-password, reset-password, and social-login, and attached rate-limiting dependency to login. |

---

## 2. API Endpoints Reference

### 2.1 Login Rate Limiting
- **Endpoint**: `POST /api/auth/login`
- **Rate Limit**: 5 attempts per 15 minutes per IP address (configurable via `LOGIN_RATE_LIMIT_REQUESTS` and `LOGIN_RATE_LIMIT_WINDOW_SECONDS`).
- **Response when rate limited**: `429 Too Many Requests`
  ```json
  {
    "detail": "Too many login attempts. Please try again in 895 seconds."
  }
  ```

---

### 2.2 Email Verification

#### Request Verification Link / Resend
- **Endpoint**: `POST /api/auth/resend-verification`
- **Request Body**:
  ```json
  {
    "email": "user@example.com"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "message": "If an unverified account with that email exists, a verification link has been sent."
  }
  ```

#### Complete Verification
- **Endpoint**: `POST /api/auth/verify-email`
- **Request Body**:
  ```json
  {
    "token": "<email_verification_jwt_token>"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "message": "Email address verified successfully."
  }
  ```

---

### 2.3 Password Reset

#### Request Password Reset
- **Endpoint**: `POST /api/auth/forgot-password`
- **Request Body**:
  ```json
  {
    "email": "user@example.com"
  }
  ```
- **Response**: `200 OK` (Always returns success to prevent user email enumeration)
  ```json
  {
    "message": "If an account with that email exists, password reset instructions have been sent."
  }
  ```

#### Complete Password Reset
- **Endpoint**: `POST /api/auth/reset-password`
- **Request Body**:
  ```json
  {
    "token": "<password_reset_jwt_token>",
    "new_password": "NewStrongPassword123!"
  }
  ```
- **Response**: `200 OK`
  ```json
  {
    "message": "Password reset successfully. You can now log in."
  }
  ```

---

### 2.4 Social OAuth Login

- **Endpoint**: `POST /api/auth/social-login`
- **Request Body**:
  ```json
  {
    "provider": "google",
    "token": "<google_id_token>",
    "display_name": "Optional Custom Name"
  }
  ```
- **Response**: `200 OK` (Standard `TokenResponse` with `access_token`, `refresh_token`, and `user` object).

*Note: For local development, development tokens formatted as `mock:email@example.com:User Name` are also supported.*

---

## 3. Environment Configuration

The following environment variables can be adjusted in `.env`:

```env
# Auth Token Expirations
EMAIL_TOKEN_EXPIRE_HOURS=24
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=15

# Rate Limiting
LOGIN_RATE_LIMIT_REQUESTS=5
LOGIN_RATE_LIMIT_WINDOW_SECONDS=900
```
