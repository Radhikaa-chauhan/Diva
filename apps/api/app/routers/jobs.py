from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.generation_job import GenerationJob, JobStatus
from app.models.reference_photo import ReferencePhoto
from app.schemas import JobCreateOut, JobDebugOut, JobStatusOut
from app.services import storage
from app.services.face_detection import SelfieValidationError, validate_selfie
from app.services.job_runner import run_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobCreateOut, status_code=202)
async def create_job(
    background_tasks: BackgroundTasks,
    reference_photo_id: str,
    selfie_image: UploadFile,
    db: Session = Depends(get_db),
) -> JobCreateOut:
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
        reference_photo_id=reference.id,
        status=JobStatus.PENDING,
        selfie_image_url=selfie_url,
        prompt_used=reference.prompt_template,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_job, job.id)

    return JobCreateOut(job_id=job.id)


@router.get("/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> GenerationJob:
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