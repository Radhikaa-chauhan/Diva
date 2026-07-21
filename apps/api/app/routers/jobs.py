"""Job creation, polling, history, favorites, deletion, search, filtering, and sorting."""
import logging
import math
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import asc, desc, func, nulls_last, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.models.user import User
from app.schemas import (
    JobCreateOut,
    JobDebugOut,
    JobHistoryOut,
    JobStatusOut,
    PaginatedResponse,
)
from app.services import storage
from app.services.face_detection import SelfieValidationError, validate_selfie
from app.services.job_runner import run_job
from app.services.stats_cache import stats_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# ── Configuration Constants ─────────────────────────────────────────────
_VALID_STATUS_VALUES = {s.value for s in JobStatus}
MAX_SELFIE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CACHE_TTL_SECONDS = 300  # 5 minutes


# ── Monitoring Placeholders ─────────────────────────────────────────────
# TODO: Integrate with Prometheus/Sentry in production
_jobs_created_count = 0
_jobs_failed_count = 0


def _check_rate_limit(user: User, db: Session) -> None:
    """Enforce per-user hourly rate limit."""
    from app.config import get_settings

    settings = get_settings()
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    count = db.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .where(
            GenerationJob.user_id == user.id,
            GenerationJob.created_at >= one_hour_ago,
            GenerationJob.is_deleted == False,  # Exclude soft-deleted jobs
        )
    )
    if (count or 0) >= settings.rate_limit_per_hour:
        logger.warning(
            "Rate limit exceeded for user_id=%s (count=%s, limit=%s)",
            user.id,
            count,
            settings.rate_limit_per_hour,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {settings.rate_limit_per_hour} generations per hour.",
        )


def _validate_selfie_upload(content_type: Optional[str], data: bytes) -> None:
    """Validate selfie file type, size, and content."""
    # Validate file size
    if len(data) > MAX_SELFIE_SIZE_BYTES:
        logger.warning(
            "Selfie upload rejected: file too large (%s bytes, max %s)",
            len(data),
            MAX_SELFIE_SIZE_BYTES,
        )
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum {MAX_SELFIE_SIZE_BYTES / 1024 / 1024:.0f}MB allowed.",
        )

    # Validate MIME type
    if (content_type or "").lower() not in ALLOWED_IMAGE_TYPES:
        logger.warning(
            "Selfie upload rejected: invalid MIME type (%s)", content_type
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}",
        )

    # Use existing validation (format, face detection, etc.)
    try:
        validate_selfie(content_type or "", data)
    except SelfieValidationError as exc:
        logger.warning("Selfie validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def resolve_date_preset(preset: str) -> tuple[datetime, datetime]:
    """Helper to convert date preset string to (start_date, end_date) UTC datetimes."""
    now = datetime.now(timezone.utc)
    preset_lower = preset.lower().strip()
    
    if preset_lower == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now
    elif preset_lower == "last_7_days":
        return now - timedelta(days=7), now
    elif preset_lower == "last_30_days":
        return now - timedelta(days=30), now
    elif preset_lower == "last_week":
        today = now.date()
        start_of_this_week = today - timedelta(days=today.weekday())
        start_of_last_week = start_of_this_week - timedelta(days=7)
        end_of_last_week = start_of_this_week - timedelta(seconds=1)
        start_dt = datetime.combine(
            start_of_last_week, datetime.min.time(), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(
            end_of_last_week, datetime.max.time(), tzinfo=timezone.utc
        )
        return start_dt, end_dt
    else:
        logger.warning("Invalid date_preset: %s", preset)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date_preset '{preset}'. Valid presets: today, last_7_days, last_30_days, last_week",
        )


def build_paginated_job_history(
    db: Session,
    user_id: str,
    page: int,
    per_page: int,
    q: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    date_preset: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    status_filter: Optional[str] = None,
    favorites_only: bool = False,
) -> PaginatedResponse[JobHistoryOut]:
    """Shared helper for paginated job listing with search, filtering, and sorting."""
    base = select(GenerationJob).where(
        GenerationJob.user_id == user_id,
        GenerationJob.is_deleted == False,  # Exclude soft-deleted jobs
    )

    # 1. Search filter (multi-column match across prompt_used, reference title & collection)
    if q and q.strip():
        search_term = f"%{q.strip()}%"
        base = base.outerjoin(GenerationJob.reference).where(
            or_(
                GenerationJob.prompt_used.ilike(search_term),
                ReferencePhoto.title.ilike(search_term),
                ReferencePhoto.collection.ilike(search_term),
            )
        )

    # 2. Date Filtering
    if date_preset:
        preset_start, preset_end = resolve_date_preset(date_preset)
        base = base.where(
            GenerationJob.created_at >= preset_start,
            GenerationJob.created_at <= preset_end,
        )
    else:
        if start_date:
            base = base.where(GenerationJob.created_at >= start_date)
        if end_date:
            base = base.where(GenerationJob.created_at <= end_date)

    # 3. Status & Favorites Filtering
    if favorites_only:
        base = base.where(
            GenerationJob.is_favorite.is_(True),
            GenerationJob.status == JobStatus.COMPLETE,
        )
    elif status_filter:
        if status_filter not in _VALID_STATUS_VALUES:
            logger.warning(
                "Invalid status filter attempted: %s, valid: %s",
                status_filter,
                _VALID_STATUS_VALUES,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status filter '{status_filter}'. Valid values: {', '.join(_VALID_STATUS_VALUES)}",
            )
        base = base.where(GenerationJob.status == status_filter)

    # Total count query
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    # 4. Multi-Criteria Sorting
    sort_by_lower = sort_by.lower().strip()
    order_lower = order.lower().strip()

    if order_lower not in ("asc", "desc"):
        logger.warning("Invalid sort order attempted: %s", order_lower)
        raise HTTPException(status_code=400, detail="Invalid order. Valid options: asc, desc")

    if sort_by_lower in ("latency", "latency_ms"):
        order_clause = (
            nulls_last(asc(GenerationJob.latency_ms))
            if order_lower == "asc"
            else nulls_last(desc(GenerationJob.latency_ms))
        )
    elif sort_by_lower in ("cost", "cost_usd"):
        order_clause = (
            nulls_last(asc(GenerationJob.cost_usd))
            if order_lower == "asc"
            else nulls_last(desc(GenerationJob.cost_usd))
        )
    elif sort_by_lower in ("created_at", "date"):
        order_clause = (
            asc(GenerationJob.created_at)
            if order_lower == "asc"
            else desc(GenerationJob.created_at)
        )
    else:
        logger.warning("Invalid sort_by field attempted: %s", sort_by)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort_by field '{sort_by}'. Valid options: created_at, latency, cost",
        )

    rows = db.scalars(
        base.options(joinedload(GenerationJob.reference))
        .order_by(order_clause, desc(GenerationJob.created_at))
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).unique().all()

    items = [
        JobHistoryOut(
            id=j.id,
            status=j.status,
            reference_title=j.reference.title if j.reference else "Unknown",
            reference_thumbnail=j.reference.thumbnail_url if j.reference else "",
            selfie_image_url=j.selfie_image_url,
            result_urls=j.result_urls,
            is_favorite=j.is_favorite,
            latency_ms=j.latency_ms,
            cost_usd=float(j.cost_usd) if j.cost_usd is not None else None,
            created_at=j.created_at,
            error=j.error_message,
        )
        for j in rows
    ]

    logger.debug(
        "Job listing for user_id=%s: total=%s, page=%s, sort_by=%s, returned=%s",
        user_id,
        total,
        page,
        sort_by,
        len(items),
    )
    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=math.ceil(total / per_page) if total else 0,
    )


@router.post("", response_model=JobCreateOut, status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    reference_photo_id: str,
    selfie_image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobCreateOut:
    """Create and queue a new generation job."""
    logger.info(
        "Job creation requested by user_id=%s, reference_photo_id=%s",
        current_user.id,
        reference_photo_id,
    )
    
    # Check rate limit
    _check_rate_limit(current_user, db)

    # Validate reference photo exists and is active
    reference = db.get(ReferencePhoto, reference_photo_id)
    if reference is None or not reference.active:
        logger.warning(
            "Invalid reference_photo_id=%s for user_id=%s",
            reference_photo_id,
            current_user.id,
        )
        raise HTTPException(
            status_code=400, detail="Unknown or inactive reference_photo_id"
        )

    # Read and validate selfie
    data = await selfie_image.read()
    logger.info(
        "Selfie uploaded: filename=%s, content_type=%s, size_bytes=%s",
        selfie_image.filename,
        selfie_image.content_type,
        len(data),
    )

    try:
        _validate_selfie_upload(selfie_image.content_type, data)
    except HTTPException:
        raise

    # Save selfie to storage
    selfie_url = storage.save_bytes(
        "selfies", selfie_image.filename or "selfie.jpg", data
    )
    logger.info("Selfie saved at url=%s", selfie_url)

    # Create job record
    job = GenerationJob(
        user_id=current_user.id,
        reference_photo_id=reference.id,
        status=JobStatus.PENDING,
        selfie_image_url=selfie_url,
        prompt_used=reference.prompt_template,
        is_deleted=False,  # Explicitly set for new records
    )
    db.add(job)

    # Increment user generation count
    current_user.generation_count = (current_user.generation_count or 0) + 1
    db.commit()
    db.refresh(job)

    # Invalidate stats cache
    stats_cache.invalidate(current_user.id)

    # Queue job for background processing. Retries live INSIDE run_job's
    # attempt loop — the only retry layer (was triple-nested before, G6).
    # Selfie bytes are passed through so the worker doesn't re-download
    # from S3/HTTP what we already have in memory (G8).
    background_tasks.add_task(run_job, job.id, data)
    logger.info("Job created and queued: job_id=%s, user_id=%s", job.id, current_user.id)

    return JobCreateOut(job_id=job.id, status=job.status, created_at=job.created_at)


@router.get("", response_model=PaginatedResponse[JobHistoryOut])
def list_jobs(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(
        12, ge=1, le=100, description="Items per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search term for prompts or reference titles"
    ),
    sort_by: str = Query(
        "created_at", description="Sort by: created_at, latency, cost"
    ),
    order: str = Query("desc", description="Sort order: asc or desc"),
    date_preset: Optional[str] = Query(
        None,
        description="Date preset: today, last_7_days, last_30_days, last_week",
    ),
    start_date: Optional[datetime] = Query(
        None, description="Start timestamp filter (ISO 8601)"
    ),
    end_date: Optional[datetime] = Query(
        None, description="End timestamp filter (ISO 8601)"
    ),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by job status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    """
    Paginated list of the current user's generation jobs with search, filtering, and sorting.
    
    Soft-deleted jobs are automatically excluded.
    """
    logger.info(
        "Listing jobs for user_id=%s, page=%s, q=%s, sort_by=%s, date_preset=%s",
        current_user.id,
        page,
        q,
        sort_by,
        date_preset,
    )
    
    # Validate pagination parameters
    if page < 1:
        logger.warning("Invalid page number: %s", page)
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    
    if per_page < 1 or per_page > 100:
        logger.warning("Invalid per_page value: %s", per_page)
        raise HTTPException(status_code=400, detail="per_page must be between 1 and 100")

    return build_paginated_job_history(
        db=db,
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        q=q,
        sort_by=sort_by,
        order=order,
        date_preset=date_preset,
        start_date=start_date,
        end_date=end_date,
        status_filter=status_filter,
    )


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobStatusOut:
    """Get current status of a job."""
    job = db.get(GenerationJob, job_id)
    
    # Distinguish between "not found" and "not authorized"
    if job is None:
        logger.error("Job not found in database: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_deleted:
        logger.warning("Attempt to access soft-deleted job: job_id=%s, user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        logger.warning(
            "Unauthorized job access attempt: job_id=%s, user_id=%s (owner: %s)",
            job_id,
            current_user.id,
            job.user_id,
        )
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    
    logger.debug("Job status polled: job_id=%s, status=%s", job_id, job.status)
    
    return JobStatusOut(
        status=job.status,
        result_urls=job.result_urls,
        error=job.error_message,
    )


@router.get("/{job_id}/debug", response_model=JobDebugOut)
def get_job_debug(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobDebugOut:
    """Get debug information for a job (prompt and attempt count)."""
    job = db.get(GenerationJob, job_id)
    
    # Distinguish between "not found" and "not authorized"
    if job is None:
        logger.error("Job not found in database: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_deleted:
        logger.warning("Attempt to access soft-deleted job debug info: job_id=%s, user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        logger.warning(
            "Unauthorized job debug access attempt: job_id=%s, user_id=%s (owner: %s)",
            job_id,
            current_user.id,
            job.user_id,
        )
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    
    logger.debug("Job debug info requested: job_id=%s", job_id)
    
    return JobDebugOut(prompt_used=job.prompt_used, attempts=job.attempts)


@router.patch("/{job_id}/favorite")
def toggle_favorite(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Toggle favorite status of a job."""
    job = db.get(GenerationJob, job_id)
    
    # Distinguish between "not found" and "not authorized"
    if job is None:
        logger.error("Job not found in database: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_deleted:
        logger.warning("Attempt to favorite soft-deleted job: job_id=%s, user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        logger.warning(
            "Unauthorized job favorite access attempt: job_id=%s, user_id=%s (owner: %s)",
            job_id,
            current_user.id,
            job.user_id,
        )
        raise HTTPException(status_code=403, detail="Not authorized to access this job")
    
    job.is_favorite = not job.is_favorite
    db.commit()

    # Invalidate stats cache
    stats_cache.invalidate(current_user.id)

    logger.info(
        "Favorite toggled: job_id=%s, is_favorite=%s, user_id=%s",
        job_id,
        job.is_favorite,
        current_user.id,
    )
    return {"is_favorite": job.is_favorite}


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a job (mark as deleted but keep data)."""
    job = db.get(GenerationJob, job_id)
    
    # Distinguish between "not found" and "not authorized"
    if job is None:
        logger.error("Job not found in database: job_id=%s", job_id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.is_deleted:
        logger.warning("Attempt to delete already soft-deleted job: job_id=%s, user_id=%s", job_id, current_user.id)
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.user_id != current_user.id:
        logger.warning(
            "Unauthorized job deletion attempt: job_id=%s, user_id=%s (owner: %s)",
            job_id,
            current_user.id,
            job.user_id,
        )
        raise HTTPException(status_code=403, detail="Not authorized to delete this job")
    
    # Soft delete: mark as deleted instead of removing from database
    job.is_deleted = True
    job.deleted_at = datetime.now(timezone.utc)
    db.commit()

    # Invalidate stats cache
    stats_cache.invalidate(current_user.id)

    logger.info("Job soft-deleted: job_id=%s, user_id=%s", job_id, current_user.id)