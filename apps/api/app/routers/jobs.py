"""Job creation, polling, history, favorites, and deletion."""
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


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
        )
    )
    if (count or 0) >= settings.rate_limit_per_hour:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {settings.rate_limit_per_hour} generations per hour.",
        )


@router.post("", response_model=JobCreateOut, status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    reference_photo_id: str,
    selfie_image: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobCreateOut:
    _check_rate_limit(current_user, db)

    reference = db.get(ReferencePhoto, reference_photo_id)
    if reference is None or not reference.active:
        raise HTTPException(status_code=400, detail="Unknown or inactive reference_photo_id")

    data = await selfie_image.read()
    try:
        validate_selfie(selfie_image.content_type or "", data)
    except SelfieValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    selfie_url = storage.save_bytes("selfies", selfie_image.filename or "selfie.jpg", data)

    job = GenerationJob(
        user_id=current_user.id,
        reference_photo_id=reference.id,
        status=JobStatus.PENDING,
        selfie_image_url=selfie_url,
        prompt_used=reference.prompt_template,
    )
    db.add(job)

    # Increment user generation count
    current_user.generation_count = (current_user.generation_count or 0) + 1
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_job, job.id)

    return JobCreateOut(job_id=job.id)


@router.get("", response_model=PaginatedResponse[JobHistoryOut])
def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PaginatedResponse[JobHistoryOut]:
    """Paginated list of the current user's generation jobs."""
    base = select(GenerationJob).where(GenerationJob.user_id == current_user.id)
    if status_filter:
        base = base.where(GenerationJob.status == status_filter)

    total = db.scalar(
        select(func.count()).select_from(base.subquery())
    ) or 0

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


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusOut:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusOut(status=job.status, result_urls=job.result_urls, error=job.error_message)


@router.get("/{job_id}/debug", response_model=JobDebugOut)
def get_job_debug(job_id: str, db: Session = Depends(get_db)) -> JobDebugOut:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobDebugOut(prompt_used=job.prompt_used, attempts=job.attempts)


@router.patch("/{job_id}/favorite")
def toggle_favorite(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    job = db.get(GenerationJob, job_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    job.is_favorite = not job.is_favorite
    db.commit()
    return {"is_favorite": job.is_favorite}


@router.delete("/{job_id}", status_code=204)
def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    job = db.get(GenerationJob, job_id)
    if job is None or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()