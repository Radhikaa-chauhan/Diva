"""JWT token creation/verification and password hashing.

Uses bcrypt for password hashing (industry standard cost-factor) and
python-jose for JWT encode/decode. Tokens carry only the user id in the
`sub` claim — all other user data is fetched from the DB on each request
so permission changes take effect immediately.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


# ── Password hashing ─────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── JWT tokens ────────────────────────────────────────────────────────

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh"},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: str = "access") -> str | None:
    """Returns user_id if valid, None otherwise."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        if payload.get("type") != expected_type:
            return None
        return payload.get("sub")
    except JWTError:
        return None
