from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator
import re

T = TypeVar("T")


# ── OAuth Provider Enum ───────────────────────────────────────────────

class OAuthProvider(str, Enum):
    GOOGLE = "google"
    GITHUB = "github"


# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


# ── Error Responses ───────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    status_code: int
    detail: str
    error_code: str | None = None

    model_config = {"from_attributes": True}


class RateLimitError(BaseModel):
    status_code: int = 429
    detail: str = "Too many requests"
    retry_after: int  # Seconds to wait
    error_code: str = "RATE_LIMIT_EXCEEDED"


# ── Auth ──────────────────────────────────────────────────────────────

class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        """Enforce password complexity."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};:,.<>?]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v):
        if not v or not v.strip():
            raise ValueError("display_name cannot be empty or whitespace-only")
        return v.strip()

    model_config = {"from_attributes": True}


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    display_name: str
    avatar_url: HttpUrl | None = None
    is_email_verified: bool = False
    is_admin: bool = False
    bio: str | None = None
    generation_count: int = Field(..., ge=0)
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # Seconds (default 1 hour)
    refresh_expires_in: int = 604800  # Seconds (default 7 days)
    user: UserOut

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    bio: str | None = Field(None, max_length=300)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("display_name cannot be empty or whitespace-only")
        return v.strip() if v else None

    @field_validator("bio")
    @classmethod
    def clean_bio(cls, v):
        return v.strip() if v else v

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    message: str

    model_config = {"from_attributes": True}


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10)

    model_config = {"from_attributes": True}


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$", description="6-digit numeric OTP code")

    model_config = {"from_attributes": True}


class SendOtpRequest(BaseModel):
    email: EmailStr

    model_config = {"from_attributes": True}


class ResendVerificationRequest(BaseModel):
    email: EmailStr

    model_config = {"from_attributes": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    model_config = {"from_attributes": True}


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        """Enforce password complexity."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};:,.<>?]", v):
            raise ValueError("Password must contain at least one special character")
        return v

    model_config = {"from_attributes": True}


class SocialLoginRequest(BaseModel):
    provider: OAuthProvider = Field(..., description="OAuth provider (google, github)")
    token: str = Field(..., min_length=10, description="OAuth token")
    display_name: str | None = Field(None, min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError("display_name cannot be empty or whitespace-only")
        return v.strip() if v else None

    model_config = {"from_attributes": True}


# ── References ────────────────────────────────────────────────────────

class ReferencePhotoOut(BaseModel):
    id: str
    title: str
    collection: str | None
    thumbnail_url: HttpUrl

    model_config = {"from_attributes": True}


class PaginatedReferences(PaginatedResponse[ReferencePhotoOut]):
    pass


# ── Jobs ──────────────────────────────────────────────────────────────

class JobCreateOut(BaseModel):
    job_id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobStatusOut(BaseModel):
    status: str
    result_urls: list[HttpUrl] | None = Field(None, max_items=100)
    error: str | None = None

    model_config = {"from_attributes": True}


class JobDebugOut(BaseModel):
    prompt_used: str | None = None
    attempts: int = Field(..., ge=1)

    model_config = {"from_attributes": True}


class JobHistoryOut(BaseModel):
    id: str
    status: str
    reference_title: str
    reference_thumbnail: HttpUrl
    selfie_image_url: HttpUrl
    result_urls: list[HttpUrl] | None = Field(None, max_items=100)
    is_favorite: bool = False
    latency_ms: int | None = Field(None, ge=0)
    cost_usd: float | None = Field(None, ge=0.0)
    created_at: datetime
    error: str | None = None

    model_config = {"from_attributes": True}


class PaginatedJobs(PaginatedResponse[JobHistoryOut]):
    pass


# ── Dashboard ─────────────────────────────────────────────────────────

class DashboardStatsOut(BaseModel):
    total_generations: int = Field(..., ge=0)
    completed_generations: int = Field(..., ge=0)
    favorites_count: int = Field(..., ge=0)
    storage_used_mb: float = Field(..., ge=0.0)

    @field_validator("completed_generations")
    @classmethod
    def validate_completed_vs_total(cls, v, info):
        """Ensure completed never exceeds total."""
        if "total_generations" in info.data:
            total = info.data["total_generations"]
            if v > total:
                raise ValueError("completed_generations cannot exceed total_generations")
        return v

    model_config = {"from_attributes": True}


# ── Social: Posts ─────────────────────────────────────────────────────

class AuthorSummary(BaseModel):
    id: str
    username: str | None = None
    display_name: str
    avatar_url: HttpUrl | None = None

    model_config = {"from_attributes": True}


class PostCreate(BaseModel):
    job_id: str
    caption: str | None = Field(None, max_length=2000)
    visibility: str = "public"

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        if v not in ("public", "private"):
            raise ValueError("visibility must be 'public' or 'private'")
        return v


class PostOut(BaseModel):
    id: str
    author: AuthorSummary
    reference_photo_id: str | None
    image_url: HttpUrl
    caption: str | None
    visibility: str
    likes_count: int = Field(..., ge=0)
    comments_count: int = Field(..., ge=0)
    saves_count: int = Field(..., ge=0)
    is_liked: bool = False
    is_saved: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedPosts(PaginatedResponse[PostOut]):
    pass


# ── Social: Follow ────────────────────────────────────────────────────

class FollowStatusOut(BaseModel):
    is_following: bool
    followers_count: int = Field(..., ge=0)


class PaginatedUsers(PaginatedResponse[AuthorSummary]):
    pass


# ── Admin ─────────────────────────────────────────────────────────────

class AdminStatsOut(BaseModel):
    total_users: int = Field(..., ge=0)
    active_24h: int = Field(..., ge=0)     # logged in within 24h
    active_7d: int = Field(..., ge=0)      # logged in within 7 days
    new_users_7d: int = Field(..., ge=0)   # signed up within 7 days
    verified_users: int = Field(..., ge=0)
    total_generations: int = Field(..., ge=0)
    total_posts: int = Field(..., ge=0)


class AdminUserOut(BaseModel):
    id: str
    email: str
    username: str | None
    display_name: str
    is_email_verified: bool
    is_active: bool
    generation_count: int = Field(..., ge=0)
    followers_count: int = Field(..., ge=0)
    last_login_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Social: Profiles ──────────────────────────────────────────────────

class ProfileOut(BaseModel):
    id: str
    username: str | None
    display_name: str
    avatar_url: HttpUrl | None = None
    bio: str | None = None
    followers_count: int = Field(..., ge=0)
    following_count: int = Field(..., ge=0)
    posts_count: int = Field(..., ge=0)
    is_following: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Social: Share to friends ──────────────────────────────────────────

class ShareCreate(BaseModel):
    user_ids: list[str] = Field(..., min_length=1, max_length=50)


class ShareResultOut(BaseModel):
    shared_with: int = Field(..., ge=0)  # how many recipients received it


class SharedPostOut(BaseModel):
    share_id: str
    sender: AuthorSummary
    post: PostOut
    is_read: bool
    created_at: datetime


class UnreadCountOut(BaseModel):
    count: int = Field(..., ge=0)


# ── Social: Engagement (likes, comments, saves) ────────────────────────

class LikeStatusOut(BaseModel):
    is_liked: bool
    likes_count: int = Field(..., ge=0)


class SaveStatusOut(BaseModel):
    is_saved: bool
    saves_count: int = Field(..., ge=0)


class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class CommentOut(BaseModel):
    id: str
    author: AuthorSummary
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedComments(PaginatedResponse[CommentOut]):
    pass