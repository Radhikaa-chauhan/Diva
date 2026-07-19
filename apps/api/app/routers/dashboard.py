import logging
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.routers.jobs import build_paginated_job_history
from app.schemas import DashboardStatsOut, JobHistoryOut, PaginatedResponse
from app.services.stats_cache import stats_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# Enums for validation
class SortField(str, Enum):
    CREATED_AT = "created_at"
    LATENCY = "latency_ms"
    COST = "cost_usd"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class DatePreset(str, Enum):
    TODAY = "today"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardStatsOut:
    """Get aggregated dashboard stats using high-performance TTL stats cache."""
    logger.info("Dashboard stats requested by user_id=%s", current_user.id)
    return stats_cache.get_stats(db, current_user)


@router.get("/history", response_model=PaginatedResponse[JobHistoryOut])
def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    q: str | None = Query(None, description="Search term for prompts or reference title"),
    sort_by: SortField = Query(SortField.CREATED_AT, description="Sort by field"),
    order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    date_preset: DatePreset | None = Query(None, description="Date preset filter"),
    start_date: datetime | None = Query(None, description="Custom start timestamp"),
    end_date: datetime | None = Query(None, description="Custom end timestamp"),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    """Get paginated generation history with search, sorting, and date range filters."""
    logger.info(
        "Dashboard history requested by user_id=%s, page=%s, q=%s, sort_by=%s, order=%s",
        current_user.id, page, q, sort_by, order,
    )
    return build_paginated_job_history(
        db=db,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        q=q,
        sort_by=sort_by.value,  # Convert enum to string
        order=order.value,
        date_preset=date_preset.value if date_preset else None,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )


@router.get("/favorites", response_model=PaginatedResponse[JobHistoryOut])
def get_favorites(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    q: str | None = Query(None, description="Search term for prompts or reference title"),
    sort_by: SortField = Query(SortField.CREATED_AT, description="Sort by field"),
    order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    date_preset: DatePreset | None = Query(None, description="Date preset filter"),
    start_date: datetime | None = Query(None, description="Custom start timestamp"),
    end_date: datetime | None = Query(None, description="Custom end timestamp"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    """Get paginated favorite generations with search, sorting, and date range filters."""
    logger.info("Dashboard favorites requested by user_id=%s, page=%s, q=%s", current_user.id, page, q)
    return build_paginated_job_history(
        db=db,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        q=q,
        sort_by=sort_by.value,
        order=order.value,
        date_preset=date_preset.value if date_preset else None,
        start_date=start_date,
        end_date=end_date,
        favorites_only=True,
    )