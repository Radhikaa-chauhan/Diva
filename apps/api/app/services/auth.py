"""JWT token creation/verification and password hashing.

Uses bcrypt for password hashing (industry standard cost-factor) and
PyJWT for JWT encode/decode. Access and refresh tokens carry only the user
id (`sub`) and a `token_version` in their claims — all other user data is
fetched from the DB on each request so permission changes take effect
immediately, and comparing `token_version` against the value stored on the
user record lets you revoke sessions (single device, or "log out
everywhere") without rotating the signing key for every user.

Social login tokens (Google, GitHub, ...) are verified against the issuing
provider before being trusted — see `verify_social_token`.

New settings this file expects, on top of what it already used:
  - settings.google_client_id   your Google OAuth client ID, used to check
                                 the token's audience claim
  - settings.environment        e.g. "development" / "test" / "production";
                                 keeps the mock social-login path out of
                                 production. Rename the getattr() lookup
                                 below if your Settings class calls this
                                 field something else.

New dependencies (only imported where used, so the rest of this module
still works if they aren't installed yet): `google-auth`, `httpx`.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_BCRYPT_MAX_BYTES = 72
_MOCK_ALLOWED_ENVIRONMENTS = {"development", "test", "local"}


# ── Password hashing ─────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hashes a password with bcrypt.

    Raises ValueError if the password is longer than bcrypt's 72-byte
    limit — validate/cap password length in your request schema so this
    shows up as a clean 400 there instead of surfacing here as a 500.
    """
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password is {len(encoded)} bytes encoded; bcrypt supports a "
            f"maximum of {_BCRYPT_MAX_BYTES} bytes."
        )
    logger.debug("Hashing password (bcrypt)")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    encoded = plain.encode("utf-8")
    if len(encoded) > _BCRYPT_MAX_BYTES:
        # Couldn't have been hashed successfully in the first place, so
        # it's definitely not a match — fail closed instead of calling bcrypt.
        logger.debug("Password verification failed: input exceeds bcrypt's byte limit")
        return False
    result = bcrypt.checkpw(encoded, hashed.encode())
    logger.debug("Password verification result=%s", result)
    return result


# ── JWT tokens ────────────────────────────────────────────────────────

def _encode(claims: dict) -> str:
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, token_version: int = 0) -> str:
    """`token_version` should be the value currently stored on the user's
    DB record. Bump that value on logout / password change / suspected
    compromise to invalidate every access and refresh token issued before
    the bump, without rotating jwt_secret_key for every other user too.
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    token = _encode({
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "token_version": token_version,
    })
    logger.info("Created access token for user_id=%s, expires=%s", user_id, expire.isoformat())
    return token


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    token = _encode({
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
        "token_version": token_version,
    })
    logger.info("Created refresh token for user_id=%s, expires=%s", user_id, expire.isoformat())
    return token


def create_email_verify_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        hours=settings.email_token_expire_hours
    )
    token = _encode({
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "email_verify",
    })
    logger.info("Created email verify token for user_id=%s, expires=%s", user_id, expire.isoformat())
    return token


def create_password_reset_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.password_reset_token_expire_minutes
    )
    token = _encode({
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),
        "type": "password_reset",
    })
    logger.info("Created password reset token for user_id=%s, expires=%s", user_id, expire.isoformat())
    return token


def decode_token(token: str, expected_type: str = "access") -> str | None:
    """Returns user_id if valid, None otherwise.

    This checks signature, expiry, and token type only. It does NOT check
    token_version — to make revocation actually take effect, use
    decode_token_payload instead and compare the `token_version` claim
    against the value stored on the user record wherever you already fetch
    the user from the DB.
    """
    payload = decode_token_payload(token, expected_type)
    return payload["sub"] if payload else None


def decode_token_payload(token: str, expected_type: str = "access") -> dict | None:
    """Returns the full validated claim set if valid, None otherwise."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != expected_type:
            logger.warning("Token type mismatch: expected=%s, got=%s", expected_type, payload.get("type"))
            return None
        logger.debug("Token decoded successfully for user_id=%s, type=%s", payload.get("sub"), expected_type)
        return payload
    except jwt.ExpiredSignatureError:
        logger.info("Token expired (type=%s)", expected_type)
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("Invalid token (type=%s): %s", expected_type, exc)
        return None


# ── Social OAuth Helpers ──────────────────────────────────────────────

def verify_social_token(provider: str, token: str) -> dict | None:
    """Verifies a social-login token against the issuing provider and
    returns the identity it belongs to, or None if it's missing, malformed,
    or fails verification.

    - Google: the token is a signed JWT (ID token) — verified against
      Google's public keys, checking signature, issuer, audience, and
      expiry via the `google-auth` library.
    - GitHub: the token is an opaque bearer token, not a JWT — there's no
      local signature to check, so it's verified by calling GitHub's API
      with it; a successful authenticated response IS the verification.

    A `mock:email@example.com:Name` token is only accepted when
    settings.environment is development/test/local, so it can't quietly
    become a login bypass in production.
    """
    logger.info("Verifying social token for provider=%s", provider)
    if not token or len(token) < 10:
        return None

    if token.startswith("mock:"):
        if getattr(settings, "environment", "production") not in _MOCK_ALLOWED_ENVIRONMENTS:
            logger.error("Rejected mock social token outside a dev/test environment")
            return None
        parts = token.split(":")
        if len(parts) < 2:
            return None
        email = parts[1]
        display_name = parts[2] if len(parts) > 2 else email.split("@")[0]
        return {"email": email, "display_name": display_name, "sub": f"{provider}_{email}"}

    provider_key = provider.lower()
    try:
        if provider_key == "google":
            return _verify_google_token(token)
        if provider_key == "github":
            return _verify_github_token(token)
    except Exception as exc:
        logger.error("Unexpected error verifying %s token: %s", provider, exc)
        return None

    logger.warning("No verifier implemented for provider=%s", provider)
    return None


def _verify_google_token(token: str) -> dict | None:
    """Verifies a Google ID token's signature, issuer, audience, and expiry.
    Requires `google-auth` (pip install google-auth) and
    settings.google_client_id.
    """
    try:
        # pyrefly: ignore [missing-import]
        from google.auth.transport import requests as google_requests
        # pyrefly: ignore [missing-import]
        from google.oauth2 import id_token as google_id_token

        payload = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), audience=settings.google_client_id
        )
    except ValueError as exc:
        logger.warning("Google token verification failed: %s", exc)
        return None
    except Exception as exc:
        logger.error("Unexpected error verifying Google token: %s", exc)
        return None

    email = payload.get("email")
    if not email or not payload.get("email_verified"):
        logger.warning("Google token has no verified email, rejecting")
        return None

    name = payload.get("name") or payload.get("given_name")
    return {"email": email, "display_name": name or email.split("@")[0], "sub": payload.get("sub")}


def _verify_github_token(token: str) -> dict | None:
    """Verifies a GitHub access token by calling GitHub's API with it.
    Requires `httpx` (pip install httpx). Runs synchronously — if this is
    called from an async route, swap in httpx.AsyncClient so it doesn't
    block the event loop.
    """
    import httpx

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        resp = httpx.get("https://api.github.com/user", headers=headers, timeout=5.0)
    except httpx.HTTPError as exc:
        logger.warning("GitHub token verification request failed: %s", exc)
        return None

    if resp.status_code != 200:
        logger.warning("GitHub token verification failed: status=%s", resp.status_code)
        return None

    data = resp.json()
    email = data.get("email")

    if not email:
        # Public profile email can be blank even for a valid token; fall
        # back to the primary verified address from /user/emails.
        try:
            emails_resp = httpx.get("https://api.github.com/user/emails", headers=headers, timeout=5.0)
            if emails_resp.status_code == 200:
                email = next(
                    (e["email"] for e in emails_resp.json() if e.get("primary") and e.get("verified")),
                    None,
                )
        except httpx.HTTPError as exc:
            logger.warning("GitHub email lookup failed: %s", exc)

    if not email:
        logger.warning("GitHub token verified but no verified email available")
        return None

    name = data.get("name") or data.get("login")
    return {"email": email, "display_name": name or email.split("@")[0], "sub": str(data.get("id"))}