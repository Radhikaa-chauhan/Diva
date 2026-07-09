"""Runs a single generation job end to end (TRD §2 sequence diagram).

Executed as a FastAPI BackgroundTask right now — good enough for V1's
traffic. If volume grows past what one process can handle, swap this for a
real queue (e.g. Celery/RQ + Redis) without touching the API layer: routes
only ever read/write `generation_jobs` rows.
"""
import io
import time

from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.generation_job import GenerationJob, JobStatus
from app.services import storage
from app.services.flux import GenerationError, generate

settings = get_settings()


def _passes_quality_gate(image_bytes: bytes) -> bool:
    """Cheap automated sanity check, not a real perceptual quality model.

    Rejects obviously-broken output (empty/near-blank images) so the retry
    path (ADR-2) has something real to trigger on. A stronger check
    (identity similarity, NSFW filter, etc.) is a natural P1 upgrade here.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception:
        return False
    histogram = image.histogram()
    dominant = max(histogram)
    return dominant < 0.98 * sum(histogram)


async def run_job(job_id: str) -> None:
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return

        started_at = time.monotonic()
        prompt = job.prompt_used

        job.status = JobStatus.GENERATING
        db.commit()

        last_error: str | None = None
        for attempt in range(1, settings.max_generation_attempts + 1):
            job.attempts = attempt
            db.commit()
            try:
                result = await generate(_load_selfie_bytes(job.selfie_image_url), prompt)
            except GenerationError as exc:
                last_error = str(exc)
                continue

            job.status = JobStatus.QUALITY_CHECK
            db.commit()

            if _passes_quality_gate(result.image_bytes):
                result_url = storage.save_bytes("results", "result.jpg", result.image_bytes)
                job.result_urls = [result_url]
                job.prompt_used = result.prompt_used
                job.cost_usd = result.cost_usd
                job.status = JobStatus.COMPLETE
                job.latency_ms = int((time.monotonic() - started_at) * 1000)
                db.commit()
                return

            prompt = f"{prompt}. Ensure the person's face and identity are sharply and clearly preserved."
            last_error = "Generated image failed the automated quality check."

        job.status = JobStatus.FAILED
        job.error_message = last_error or "Generation failed after all retry attempts."
        job.latency_ms = int((time.monotonic() - started_at) * 1000)
        db.commit()
    finally:
        db.close()


def _load_selfie_bytes(selfie_url: str) -> bytes:
    key = selfie_url.split("/storage/", 1)[1]
    path = settings.storage_dir / key
    return path.read_bytes()