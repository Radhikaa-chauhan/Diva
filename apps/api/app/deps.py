"""Reusable FastAPI dependencies for authentication, authorization, and security checks."""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.services.auth import decode_token_payload

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Require a valid, active access token.
    
    Verifies:
    - JWT signature and expiration
    - Soft delete and account active status
    - Token version matching (token revocation / logout validation)
    
    Returns the authenticated User or raises 401 Unauthorized.
    """
    if credentials is None or not credentials.credentials:
        logger.debug("Authentication failed: No bearer credentials provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # 1. Decode token payload and verify type
        payload = decode_token_payload(token, expected_type="access")
        if not payload or "sub" not in payload:
            logger.warning("Authentication failed: Invalid or expired access token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = payload["sub"]
        token_version = payload.get("token_version", 0)

        # 2. Single DB query for user
        user = db.get(User, user_id)

        # 3. Verify user existence, active status, and soft delete state
        if user is None or not user.is_active or getattr(user, "is_deleted", False):
            logger.warning("Authentication failed: User user_id=%s not found, inactive, or deleted", user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or account is inactive.",
            )

        # 4. Token version revocation check (logout / session invalidation)
        user_token_version = getattr(user, "token_version", 0)
        if token_version != user_token_version:
            logger.warning("Authentication failed: Revoked token presented for user_id=%s (version mismatch: %d vs %d)", user_id, token_version, user_token_version)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session has been revoked or logged out.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Log sanitized user ID without logging PII (email)
        logger.debug("Successfully authenticated user_id=%s", user.id)
        return user

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during authentication: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None for unauthenticated requests
    instead of raising — useful for endpoints that work with or without auth.
    """
    if credentials is None or not credentials.credentials:
        return None

    try:
        payload = decode_token_payload(credentials.credentials, expected_type="access")
        if not payload or "sub" not in payload:
            return None

        user_id = payload["sub"]
        token_version = payload.get("token_version", 0)

        user = db.get(User, user_id)
        if user is None or not user.is_active or getattr(user, "is_deleted", False):
            return None

        if token_version != getattr(user, "token_version", 0):
            return None

        logger.debug("Optionally authenticated user_id=%s", user.id)
        return user
    except Exception as exc:
        logger.debug("Optional authentication check failed: %s", exc)
        return None


def require_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that enforces email verification before granting access to sensitive routes."""
    if not current_user.is_email_verified:
        logger.warning("Access denied: User user_id=%s has unverified email", current_user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required to access this resource.",
        )
    return current_user
