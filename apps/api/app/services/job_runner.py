"""Runs a single generation job end to end (TRD §2 sequence diagram).

Executed as a FastAPI BackgroundTask right now — good enough for V1's
traffic. If volume grows past what one process can handle, swap this for a
real queue (e.g. Celery/RQ + Redis) without touching the API layer: routes
only ever read/write `generation_jobs` rows.
"""
import io
import time
import logging
import asyncio

from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models.generation_job import GenerationJob, JobStatus
from app.models.user import User
from app.services import storage
from app.services.flux import GenerationError, generate

# Configure structured-like console logging for production observability
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("job_runner")

settings = get_settings()


def _passes_quality_gate(image_bytes: bytes) -> bool:
    """Cheap automated sanity check, not a real perceptual quality model.

    Rejects obviously-broken output (empty/near-blank images) so the retry
    path (ADR-2) has something real to trigger on.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("L")
    except Exception as e:
        logger.warning(f"Failed to open image for quality gate: {e}")
        return False
    histogram = image.histogram()
    dominant = max(histogram)
    return dominant < 0.98 * sum(histogram)


async def run_job(job_id: str) -> None:
    logger.info(f"Starting generation job={job_id}")
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            logger.error(f"Job={job_id} not found in database")
            return

        started_at = time.monotonic()
        prompt = job.prompt_used

        job.status = JobStatus.GENERATING
        db.commit()

        last_error: str | None = None
        for attempt in range(1, settings.max_generation_attempts + 1):
            logger.info(f"Running generation attempt={attempt}/{settings.max_generation_attempts} for job={job_id}")
            job.attempts = attempt
            db.commit()
            
            try:
                # Add a 60-second timeout guard to prevent hung HTTP request loops
                result = await asyncio.wait_for(
                    generate(_load_selfie_bytes(job.selfie_image_url), prompt),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Flux generation timed out on attempt={attempt} for job={job_id}")
                last_error = "Flux API call timed out"
                continue
            except GenerationError as exc:
                logger.error(f"Flux generation service error on attempt={attempt} for job={job_id}: {exc}")
                last_error = str(exc)
                continue
            except Exception as exc:
                logger.exception(f"Unexpected error on attempt={attempt} for job={job_id}: {exc}")
                last_error = f"Unexpected generation error: {exc}"
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
                
                # Update user storage tracking metrics
                try:
                    user = db.get(User, job.user_id)
                    if user:
                        res_size = storage.get_file_size(result_url)
                        selfie_size = storage.get_file_size(job.selfie_image_url)
                        user.storage_used_bytes = (user.storage_used_bytes or 0) + res_size + selfie_size
                        logger.info(f"Updated user={user.id} storage footprint by {res_size + selfie_size} bytes")
                except Exception as e:
                    logger.exception(f"Failed to update storage telemetry for user={job.user_id}: {e}")

                db.commit()
                logger.info(f"Job={job_id} successfully completed in {job.latency_ms}ms")
                return

            logger.warning(f"Job={job_id} failed quality gate check on attempt={attempt}")
            prompt = f"{prompt}. Ensure the person's face and identity are sharply and clearly preserved."
            last_error = "Generated image failed the automated quality check."

        job.status = JobStatus.FAILED
        job.error_message = last_error or "Generation failed after all retry attempts."
        job.latency_ms = int((time.monotonic() - started_at) * 1000)
        db.commit()
        logger.error(f"Job={job_id} failed permanently in {job.latency_ms}ms. Error: {job.error_message}")
    except Exception as exc:
        logger.exception(f"Fatal crash inside run_job worker context for job={job_id}: {exc}")
    finally:
        db.close()


def _load_selfie_bytes(selfie_url: str) -> bytes:
    key = selfie_url.split("/storage/", 1)[1]
    path = settings.storage_dir / key
    return path.read_bytes()