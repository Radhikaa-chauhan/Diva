"""Authentication endpoints — signup, login, token refresh, profile, email verification, password reset, and social auth."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas import (
    ForgotPasswordRequest,
    MessageResponse,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SocialLoginRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserLogin,
    UserOut,
    UserSignup,
    VerifyEmailRequest,
)
from app.services.auth import (
    create_access_token,
    create_email_verify_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_social_token,
)
from app.services.rate_limiter import login_rate_limiter, rate_limit_login

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user),
    )


@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(body: UserSignup, db: Session = Depends(get_db)) -> TokenResponse:
    logger.info("Signup attempt for email=%s", body.email)
    existing = db.scalars(select(User).where(User.email == body.email)).first()
    if existing:
        logger.warning("Signup failed — email already exists: %s", body.email)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        is_email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate and log email verification token
    verify_token = create_email_verify_token(user.id)
    logger.info(
        "User signed up successfully: user_id=%s, email=%s. Verification token generated: %s",
        user.id,
        user.email,
        verify_token,
    )

    return _build_token_response(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit_login)],
)
def login(
    body: UserLogin,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    logger.info("Login attempt for email=%s", body.email)
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        logger.warning("Login failed — invalid credentials for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        logger.warning("Login failed — account deactivated: user_id=%s", user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    # Reset rate limit tracker on successful login
    client_ip = request.client.host if request.client else "127.0.0.1"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    login_rate_limiter.reset(client_ip)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Login successful: user_id=%s, email=%s", user.id, user.email)
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    logger.info("Token refresh requested")
    user_id = decode_token(body.refresh_token, expected_type="refresh")
    if user_id is None:
        logger.warning("Token refresh failed — invalid or expired refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        logger.warning("Token refresh failed — user not found or deactivated: user_id=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated.",
        )
    logger.info("Token refreshed successfully for user_id=%s", user_id)
    return _build_token_response(user)


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)) -> UserOut:
    logger.debug("Profile fetched for user_id=%s", current_user.id)
    return UserOut.model_validate(current_user)


@router.patch("/me", response_model=UserOut)
def update_me(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    if body.display_name is not None:
        logger.info("Profile updated for user_id=%s: display_name changed", current_user.id)
        current_user.display_name = body.display_name
    db.commit()
    db.refresh(current_user)
    return UserOut.model_validate(current_user)


# ── Email Verification ────────────────────────────────────────────────

@router.post("/verify-email", response_model=MessageResponse)
def verify_email(
    body: VerifyEmailRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Verify email address using verification token."""
    logger.info("Email verification attempt")
    user_id = decode_token(body.token, expected_type="email_verify")
    if user_id is None:
        logger.warning("Email verification failed — invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token.",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if user.is_email_verified:
        return MessageResponse(message="Email is already verified.")

    user.is_email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Email verified successfully for user_id=%s", user.id)
    return MessageResponse(message="Email address verified successfully.")


@router.post("/resend-verification", response_model=MessageResponse)
def resend_verification(
    body: ResendVerificationRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Resend email verification token."""
    logger.info("Resend verification requested for email=%s", body.email)
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user and not user.is_email_verified:
        token = create_email_verify_token(user.id)
        logger.info("Verification token generated for email=%s: %s", user.email, token)

    return MessageResponse(
        message="If an unverified account with that email exists, a verification link has been sent."
    )


# ── Password Reset ────────────────────────────────────────────────────

@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Request a password reset link/token."""
    logger.info("Password reset requested for email=%s", body.email)
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user and user.is_active:
        reset_token = create_password_reset_token(user.id)
        logger.info(
            "Password reset token generated for user_id=%s, email=%s: %s",
            user.id,
            user.email,
            reset_token,
        )

    # Standard security practice: return success regardless to prevent user enumeration
    return MessageResponse(
        message="If an account with that email exists, password reset instructions have been sent."
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Reset password using reset token."""
    logger.info("Password reset completion attempt")
    user_id = decode_token(body.token, expected_type="password_reset")
    if user_id is None:
        logger.warning("Password reset failed — invalid or expired token")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found or account deactivated.",
        )

    user.password_hash = hash_password(body.new_password)
    db.commit()
    logger.info("Password reset successfully for user_id=%s", user.id)
    return MessageResponse(message="Password reset successfully. You can now log in.")


# ── Social OAuth Login ────────────────────────────────────────────────

@router.post("/social-login", response_model=TokenResponse)
def social_login(
    body: SocialLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate or register user via OAuth provider token (Google, GitHub, etc.)."""
    logger.info("Social login attempt for provider=%s", body.provider)
    payload = verify_social_token(body.provider, body.token)
    if payload is None or "email" not in payload:
        logger.warning("Social login failed — invalid token for provider=%s", body.provider)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or unverified {body.provider} token.",
        )

    email = payload["email"]
    display_name = body.display_name or payload.get("display_name") or email.split("@")[0]

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        logger.info("Creating new user from social login: email=%s, provider=%s", email, body.provider)
        user = User(
            email=email,
            password_hash=hash_password(f"social-oauth-{body.provider}-{email}"),
            display_name=display_name,
            is_email_verified=True,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is deactivated.",
            )
        if not user.is_email_verified:
            user.is_email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Social login successful for user_id=%s, email=%s", user.id, user.email)
    return _build_token_response(user)