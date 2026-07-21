"""Runs a single generation job end-to-end as a FastAPI BackgroundTask.

Optimized worker (G6-G8, G10, G11):
- ONE retry layer: the attempt loop below. No tenacity wrapper, no nested
  provider retries.
- Selfie bytes are passed in from create_job — no S3/HTTP re-download of
  an upload we just had in memory. URL loading remains as fallback only.
- DB sessions are short: claim the job, close; generate with no session
  held; reopen to write the outcome. No connection pinned across network I/O.
- Quality gate is dimensions + dominant-color only (the fake "entropy"
  math is gone).

For higher volume, swap for Celery/RQ + Redis without touching the API
layer: routes only read/write `generation_jobs` rows.
"""
import asyncio
import io
import logging
import time
from typing import Optional

import httpx
from PIL import Image

from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal
from app.models.generation_job import GenerationJob, JobStatus
from app.services import storage
from app.services.flux import generate, GenerationError, InputValidationError

logger = logging.getLogger(__name__)

settings = get_settings()

MAX_GENERATION_ATTEMPTS = 3  # Hard cap (overrides settings.max_generation_attempts)
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 10.0  # seconds
SELFIE_LOAD_TIMEOUT = 30.0  # seconds
GENERATION_TIMEOUT = 120.0  # seconds — img2img models can cold-start slowly
IMAGE_MIN_WIDTH = 64
IMAGE_MIN_HEIGHT = 64
IMAGE_MAX_WIDTH = 4096
IMAGE_MAX_HEIGHT = 4096
HISTOGRAM_DOMINANT_THRESHOLD = 0.95  # >95% same-color pixels = blank/broken


class SelfieLoadError(Exception):
    """Raised when selfie cannot be loaded or is corrupted."""


# ── Quality Gate ─────────────────────────────────────────────────────

def _passes_quality_gate(image_bytes: bytes) -> bool:
    """Reject corrupted, wrongly-sized, or near-blank images."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        width, height = image.size

        if not (IMAGE_MIN_WIDTH <= width <= IMAGE_MAX_WIDTH
                and IMAGE_MIN_HEIGHT <= height <= IMAGE_MAX_HEIGHT):
            logger.warning("Image dimensions out of range: %sx%s", width, height)
            return False

        histogram = image.convert("L").histogram()
        total_pixels = sum(histogram)
        if total_pixels == 0:
            return False
        if max(histogram) / total_pixels > HISTOGRAM_DOMINANT_THRESHOLD:
            logger.warning("Image too uniform — likely blank output")
            return False

        return True
    except Exception as exc:
        logger.error("Quality gate could not read image: %s", exc)
        return False


# ── Selfie Loading (fallback only — normally bytes are passed in) ────

async def _load_selfie_bytes(selfie_url: str) -> bytes:
    """Load selfie from S3, HTTP/HTTPS, or local disk."""
    if not selfie_url or not isinstance(selfie_url, str):
        raise SelfieLoadError("Selfie URL is empty or invalid.")

    if selfie_url.startswith(("http://", "https://")) and ".amazonaws.com/" in selfie_url:
        s3_bytes = await _try_load_from_s3(selfie_url)
        if s3_bytes:
            return s3_bytes

    if selfie_url.startswith(("http://", "https://")):
        return await _load_from_http(selfie_url)

    return _load_from_disk(selfie_url)


async def _try_load_from_s3(selfie_url: str) -> Optional[bytes]:
    """Fetch from S3 in a thread; None if unconfigured or the call fails."""
    if not getattr(settings, "aws_s3_bucket_name", None):
        return None

    try:
        def _fetch_s3():
            import boto3

            key = storage.extract_s3_key(selfie_url)
            s3_client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
            obj = s3_client.get_object(Bucket=settings.aws_s3_bucket_name, Key=key)
            return obj["Body"].read()

        return await asyncio.to_thread(_fetch_s3)
    except Exception as exc:
        logger.debug("S3 load failed for %s (will try HTTP): %s", selfie_url, exc)
        return None


async def _load_from_http(selfie_url: str) -> bytes:
    """Single HTTP fetch — retries are the attempt loop's job."""
    try:
        async with httpx.AsyncClient(timeout=SELFIE_LOAD_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(selfie_url)
    except httpx.HTTPError as exc:
        raise SelfieLoadError(f"Selfie HTTP load failed: {exc}") from exc

    if resp.status_code != 200:
        raise SelfieLoadError(f"Selfie URL returned HTTP {resp.status_code}")
    return resp.content


def _load_from_disk(selfie_url: str) -> bytes:
    """Load selfie from local disk with path-traversal protection."""
    if "/storage/" in selfie_url:
        key = selfie_url.split("/storage/", 1)[1]
    else:
        key = selfie_url.lstrip("/")

    storage_root = settings.storage_dir.resolve()
    resolved = (settings.storage_dir / key).resolve()
    try:
        resolved.relative_to(storage_root)
    except ValueError:
        logger.error("Path traversal attempt: %s not under %s", resolved, storage_root)
        raise PermissionError("Access denied: path is outside storage directory")

    if not resolved.is_file():
        raise SelfieLoadError(f"Selfie file not found: {selfie_url}")
    return resolved.read_bytes()


# ── Main Job Worker ──────────────────────────────────────────────────

async def run_job(job_id: str, selfie_bytes: bytes | None = None) -> None:
    """Execute a generation job. Retries internally; writes COMPLETE or FAILED."""
    logger.info("Starting generation job=%s", job_id)

    # Session 1: claim the job, snapshot what we need, release the connection.
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            logger.error("Job=%s not found", job_id)
            return
        if job.status in (JobStatus.COMPLETE, JobStatus.FAILED):
            logger.info("Job=%s already %s, skipping", job_id, job.status)
            return

        job.status = JobStatus.GENERATING
        db.commit()
        selfie_url = job.selfie_image_url
        base_prompt = job.prompt_used
        user_id = job.user_id
    finally:
        db.close()

    # Generate with NO db session held (G7).
    started_at = time.monotonic()
    max_attempts = min(getattr(settings, "max_generation_attempts", 3), MAX_GENERATION_ATTEMPTS)
    prompt = base_prompt
    errors: list[str] = []
    result = None
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        logger.info("Generation attempt %s/%s for job=%s", attempt, max_attempts, job_id)
        try:
            if selfie_bytes is None:
                selfie_bytes = await asyncio.wait_for(
                    _load_selfie_bytes(selfie_url), timeout=SELFIE_LOAD_TIMEOUT
                )
            candidate = await asyncio.wait_for(
                generate(selfie_bytes, prompt), timeout=GENERATION_TIMEOUT
            )
        except asyncio.TimeoutError:
            errors.append(f"Timed out after {GENERATION_TIMEOUT:.0f}s")
        except (GenerationError, InputValidationError, SelfieLoadError) as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"Unexpected error: {exc}")
            logger.exception("Unexpected error on attempt %s for job=%s", attempt, job_id)
        else:
            if _passes_quality_gate(candidate.image_bytes):
                result = candidate
                break
            errors.append("Generated image failed quality check")
            prompt = (
                f"{base_prompt} "
                "[Higher quality. Sharp focus on face. Clear identity preservation.]"
            )

        if attempt < max_attempts:
            delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY)
            await asyncio.sleep(delay)

    latency_ms = int((time.monotonic() - started_at) * 1000)

    # Save the result BEFORE opening the outcome session — storage I/O
    # must not hold a DB connection either.
    result_url = None
    if result is not None:
        try:
            result_url = storage.save_bytes("results", f"{job_id}.jpg", result.image_bytes)
        except Exception as exc:
            logger.error("Failed to save result for job=%s: %s", job_id, exc)
            errors.append(f"Storage error: {exc}")
            result = None

    # Session 2: write the outcome.
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            logger.error("Job=%s vanished before outcome write", job_id)
            return

        job.attempts = attempts
        job.latency_ms = latency_ms
        if result is not None and result_url:
            job.result_urls = [result_url]
            job.prompt_used = result.prompt_used
            job.cost_usd = result.cost_usd
            job.status = JobStatus.COMPLETE

            # Best-effort storage telemetry (local files only).
            try:
                total = storage.get_file_size(job.selfie_image_url) + storage.get_file_size(result_url)
                if total:
                    db.execute(
                        text("UPDATE users SET storage_used_bytes = storage_used_bytes + :size WHERE id = :uid"),
                        {"size": total, "uid": user_id},
                    )
            except Exception as exc:
                logger.warning("Storage telemetry update failed: %s", exc)

            logger.info(
                "Job=%s COMPLETE: latency=%sms, attempts=%s", job_id, latency_ms, attempts
            )
        else:
            job.status = JobStatus.FAILED
            job.error_message = " | ".join(errors) or "Generation failed"
            logger.error("Job=%s FAILED after %s attempts: %s", job_id, attempts, job.error_message)

        db.commit()
    except Exception as exc:
        logger.exception("Failed to write outcome for job=%s: %s", job_id, exc)
        raise
    finally:
        db.close()
        try:
            from app.services.stats_cache import stats_cache

            stats_cache.invalidate(user_id)
        except Exception as exc:
            logger.error("Stats cache invalidation failed for user=%s: %s", user_id, exc)
