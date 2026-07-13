"""Dashboard endpoints — aggregated stats, history with filters, favorites."""
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import User
from app.schemas import DashboardStatsOut, JobHistoryOut, PaginatedResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsOut)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardStatsOut:
    base = select(GenerationJob).where(GenerationJob.user_id == current_user.id)

    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

    completed = db.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.user_id == current_user.id,
            GenerationJob.status == JobStatus.COMPLETE,
        )
    ) or 0

    favorites = db.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.user_id == current_user.id,
            GenerationJob.is_favorite.is_(True),
        )
    ) or 0

    storage_bytes = current_user.storage_used_bytes or 0
    storage_mb = round(storage_bytes / (1024 * 1024), 2)

    return DashboardStatsOut(
        total_generations=total,
        completed_generations=completed,
        favorites_count=favorites,
        storage_used_mb=storage_mb,
    )


@router.get("/history", response_model=PaginatedResponse[JobHistoryOut])
def get_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    base = select(GenerationJob).where(GenerationJob.user_id == current_user.id)
    if status_filter:
        base = base.where(GenerationJob.status == status_filter)

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.scalars(
        base.order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    items = [
        JobHistoryOut(
            id=j.id,
            status=j.status,
            reference_title=j.reference.title if j.reference else "Unknown",
            reference_thumbnail=j.reference.thumbnail_url if j.reference else "",
            selfie_image_url=j.selfie_image_url,
            result_urls=j.result_urls,
            is_favorite=j.is_favorite,
            created_at=j.created_at,
            error=j.error_message,
        )
        for j in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.get("/favorites", response_model=PaginatedResponse[JobHistoryOut])
def get_favorites(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    base = (
        select(GenerationJob)
        .where(
            GenerationJob.user_id == current_user.id,
            GenerationJob.is_favorite.is_(True),
            GenerationJob.status == JobStatus.COMPLETE,
        )
    )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = db.scalars(
        base.order_by(GenerationJob.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    items = [
        JobHistoryOut(
            id=j.id,
            status=j.status,
            reference_title=j.reference.title if j.reference else "Unknown",
            reference_thumbnail=j.reference.thumbnail_url if j.reference else "",
            selfie_image_url=j.selfie_image_url,
            result_urls=j.result_urls,
            is_favorite=j.is_favorite,
            created_at=j.created_at,
            error=j.error_message,
        )
        for j in rows
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )
