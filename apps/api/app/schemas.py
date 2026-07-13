from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


# ── Pagination ────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int


# ── Auth ──────────────────────────────────────────────────────────────

class UserSignup(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: str | None
    generation_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)


# ── References ────────────────────────────────────────────────────────

class ReferencePhotoOut(BaseModel):
    id: str
    title: str
    collection: str | None
    thumbnail_url: str

    model_config = {"from_attributes": True}


# ── Jobs ──────────────────────────────────────────────────────────────

class JobCreateOut(BaseModel):
    job_id: str


class JobStatusOut(BaseModel):
    status: str
    result_urls: list[str] | None
    error: str | None

    model_config = {"from_attributes": True}


class JobDebugOut(BaseModel):
    prompt_used: str | None
    attempts: int


class JobHistoryOut(BaseModel):
    id: str
    status: str
    reference_title: str
    reference_thumbnail: str
    selfie_image_url: str
    result_urls: list[str] | None
    is_favorite: bool
    created_at: datetime
    error: str | None

    model_config = {"from_attributes": True}


# ── Dashboard ─────────────────────────────────────────────────────────

class DashboardStatsOut(BaseModel):
    total_generations: int
    completed_generations: int
    favorites_count: int
    storage_used_mb: float