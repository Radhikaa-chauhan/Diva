"""Authentication endpoints — signup, login, token refresh, profile, email verification, password reset, and social auth."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.schemas import (
    ForgotPasswordRequest,
    MessageResponse,
    RefreshRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SendOtpRequest,
    SocialLoginRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserLogin,
    UserOut,
    UserSignup,
    VerifyEmailRequest,
    VerifyOtpRequest,
)
from app.services.auth import (
    create_access_token,
    create_email_verify_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    hash_password,
    verify_otp,
    verify_password,
    verify_social_token,
)
from app.services.email import send_email
from app.services.rate_limiter import login_rate_limiter, rate_limit_login

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _unique_username(db: Session, email: str) -> str:
    """Derive a unique handle from the email local-part (bob@x.com -> bob, bob2, ...)."""
    base = "".join(c for c in email.split("@")[0].lower() if c.isalnum() or c in "._")[:30] or "user"
    candidate, n = base, 1
    while db.scalars(select(User).where(User.username == candidate)).first() is not None:
        n += 1
        candidate = f"{base}{n}"
    return candidate


def _build_token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        refresh_expires_in=settings.refresh_token_expire_days * 86400,
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

    otp_code = generate_otp(6)
    otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    user = User(
        email=body.email,
        username=_unique_username(db, body.email),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        is_email_verified=False,
        otp_code=otp_code,
        otp_expires_at=otp_expires_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    send_email(
        user.email,
        "Your Diva verification code",
        f"Welcome to Diva!\n\nYour verification code is: {otp_code}\n\nIt expires in 10 minutes.",
    )
    logger.info("User signed up: user_id=%s, verification OTP emailed", user.id)

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
    login_rate_limiter.reset(client_ip, reason="successful_login")

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
        send_email(
            user.email,
            "Verify your Diva email",
            f"Your email verification token:\n\n{token}\n\nIt expires in {settings.email_token_expire_hours} hours.",
        )
        logger.info("Verification token emailed for user_id=%s", user.id)

    return MessageResponse(
        message="If an unverified account with that email exists, a verification link has been sent."
    )


@router.post("/send-otp", response_model=MessageResponse)
def send_otp(
    body: SendOtpRequest,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Generate and send a 6-digit OTP code to the requested email."""
    logger.info("OTP generation requested for email=%s", body.email)
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user:
        otp_code = generate_otp(6)
        user.otp_code = otp_code
        user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.commit()
        send_email(
            user.email,
            "Your Diva login code",
            f"Your one-time code is: {otp_code}\n\nIt expires in 10 minutes.",
        )
        logger.info("OTP generated and emailed for user_id=%s", user.id)

    # Same response either way — never reveal account existence, never leak the code.
    return MessageResponse(
        message="If an account with that email exists, an OTP code has been sent."
    )


@router.post("/verify-otp", response_model=TokenResponse)
def verify_otp_endpoint(
    body: VerifyOtpRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Verify email address using 6-digit OTP code and return authentication tokens."""
    logger.info("OTP verification attempt for email=%s", body.email)
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user is None or not user.is_active or getattr(user, "is_deleted", False):
        logger.warning("OTP verification failed — user not found or inactive for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found or inactive.",
        )

    if not verify_otp(user, body.otp):
        logger.warning("OTP verification failed — invalid or expired OTP code for email=%s", body.email)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP code.",
        )

    # Mark user email as verified and clear OTP
    user.is_email_verified = True
    user.email_verified_at = datetime.now(timezone.utc)
    user.otp_code = None
    user.otp_expires_at = None
    db.commit()
    db.refresh(user)

    logger.info("🔑 Email address verified successfully via OTP for user_id=%s (email=%s)", user.id, user.email)
    return _build_token_response(user)


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
        send_email(
            user.email,
            "Reset your Diva password",
            f"Your password reset token:\n\n{reset_token}\n\n"
            f"It expires in {settings.password_reset_token_expire_minutes} minutes. "
            "If you didn't request this, ignore this email.",
        )
        logger.info("Password reset token emailed for user_id=%s", user.id)

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
    provider_str = body.provider.value if hasattr(body.provider, "value") else str(body.provider)
    logger.info("Social login attempt for provider=%s", provider_str)
    payload = verify_social_token(provider_str, body.token)
    if payload is None or "email" not in payload:
        logger.warning("Social login failed — invalid token for provider=%s", provider_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or unverified {provider_str} token.",
        )

    email = payload["email"]
    display_name = body.display_name or payload.get("display_name") or email.split("@")[0]

    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        logger.info("Creating new user from social login: email=%s, provider=%s", email, body.provider)
        user = User(
            email=email,
            username=_unique_username(db, email),
            password_hash=hash_password(f"social-oauth-{provider_str[:10]}"),
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