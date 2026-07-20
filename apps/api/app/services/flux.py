"""Image generation adapter — Hugging Face only.

Uses Hugging Face Serverless Inference API for image generation.
Falls back to mock (local PIL filters) when HF key is not set.

Handles retries, cold starts, transient failures, and input validation.
"""
import asyncio
import base64
import io
import logging
import time
from dataclasses import dataclass

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Constants
MAX_PROMPT_LENGTH = 1000
MIN_PROMPT_LENGTH = 1
MAX_IMAGE_SIZE_MB = 50

# Exponential backoff for transient failures
_RETRY_BASE_DELAY = 0.5  # seconds
_RETRY_MAX_DELAY = 30.0
_RETRY_MAX_ATTEMPTS = 3


@dataclass
class GenerationResult:
    image_bytes: bytes
    content_type: str
    cost_usd: float
    prompt_used: str
    provider_used: str  # "huggingface" or "mock"


class GenerationError(Exception):
    """Raised when image generation fails after all retries."""
    pass


class InputValidationError(GenerationError):
    """Raised when input validation fails."""
    pass


# ── Startup Validation ───────────────────────────────────────────────

def _validate_settings():
    """Validate settings at startup."""
    if not hasattr(settings, "max_selfie_size_mb"):
        logger.warning("settings.max_selfie_size_mb not set, defaulting to 10MB")
        settings.max_selfie_size_mb = 10

    hf_key = getattr(settings, "huggingface_api_key", None)
    hf_model = getattr(settings, "huggingface_model", None)

    if hf_key and not hf_model:
        raise ValueError(
            "HUGGINGFACE_API_KEY is set but HUGGINGFACE_MODEL is not. "
            "Set both or neither."
        )

    if hf_key and not hf_model.strip():
        raise ValueError("HUGGINGFACE_MODEL cannot be empty.")

    logger.info("Settings validated: HF configured=%s", bool(hf_key))


_validate_settings()


# ── Input Validation ─────────────────────────────────────────────────

def _validate_inputs(selfie_bytes: bytes, prompt_template: str) -> None:
    """Validate image and prompt before sending to provider."""
    if not selfie_bytes:
        raise InputValidationError("Selfie image is empty.")

    max_bytes = getattr(settings, "max_selfie_size_mb", 10) * 1024 * 1024
    if len(selfie_bytes) > max_bytes:
        raise InputValidationError(
            f"Selfie is {len(selfie_bytes)} bytes; max is {max_bytes} bytes."
        )

    if not prompt_template or not isinstance(prompt_template, str):
        raise InputValidationError("Prompt must be a non-empty string.")

    if len(prompt_template) < MIN_PROMPT_LENGTH:
        raise InputValidationError(f"Prompt must be at least {MIN_PROMPT_LENGTH} character.")

    if len(prompt_template) > MAX_PROMPT_LENGTH:
        raise InputValidationError(
            f"Prompt is {len(prompt_template)} chars; max is {MAX_PROMPT_LENGTH}."
        )

    # Validate image actually opens
    try:
        img = Image.open(io.BytesIO(selfie_bytes))
        img.verify()
    except Exception as exc:
        raise InputValidationError(f"Selfie image is corrupted or unreadable: {exc}") from exc


# ── Retry Logic with Exponential Backoff ────────────────────────────

async def _retry_with_backoff(
    coro_fn,
    *args,
    max_attempts: int = _RETRY_MAX_ATTEMPTS,
    base_delay: float = _RETRY_BASE_DELAY,
    max_delay: float = _RETRY_MAX_DELAY,
):
    """Generic retry wrapper with exponential backoff.

    Args:
        coro_fn: async function to call
        *args: arguments to pass to coro_fn
        max_attempts: max number of attempts (default 3)
        base_delay: initial delay in seconds (default 0.5)
        max_delay: max delay between retries (default 30)

    Returns:
        Result from coro_fn if it succeeds
    """
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn(*args)
        except Exception as exc:
            last_exc = exc
            is_transient = isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))
            http_code = getattr(exc, "status_code", None)
            is_transient_http = http_code in (408, 429, 500, 502, 503, 504)

            if not (is_transient or is_transient_http) or attempt == max_attempts:
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed: {exc}. "
                f"Retrying in {delay:.1f}s..."
            )
            await asyncio.sleep(delay)

    if last_exc is not None:
        raise last_exc


# ── Main Entry Point ─────────────────────────────────────────────────

async def generate(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    """Generate an image from a selfie and prompt.

    Uses Hugging Face if API key is configured, otherwise falls back to mock.
    """
    _validate_inputs(selfie_bytes, prompt_template)

    hf_key = getattr(settings, "huggingface_api_key", None)
    if hf_key:
        try:
            logger.info("Attempting Hugging Face generation...")
            return await _generate_with_huggingface(selfie_bytes, prompt_template)
        except GenerationError as exc:
            logger.error(f"Hugging Face generation failed: {exc}. Falling back to mock.")

    # Fallback to mock
    logger.info("Using mock generator (HF API key not configured).")
    return await _generate_mock(selfie_bytes, prompt_template)


# ── Mock Provider ────────────────────────────────────────────────────

async def _generate_mock(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    """Local PIL-based generation for dev/test ($0)."""
    logger.debug("Mock generation started, selfie_size=%s bytes", len(selfie_bytes))

    def _apply_filter() -> bytes:
        try:
            from PIL import ImageEnhance, ImageOps

            image = Image.open(io.BytesIO(selfie_bytes)).convert("RGB")
            # Apply EXIF rotation if present
            image = ImageOps.exif_transpose(image)
            # Grayscale + colorize for a sepia tone effect
            image = ImageOps.colorize(
                ImageOps.grayscale(image),
                black="#1a1024",
                white="#f4d9a0",
                mid="#b5673d",
            )
            image = ImageEnhance.Contrast(image).enhance(1.15)
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=90)
            return buf.getvalue()
        except Exception as exc:
            logger.error(f"Mock filter failed: {exc}")
            raise GenerationError(f"Mock generation filter failed: {exc}") from exc

    # Simulate generation latency
    await asyncio.sleep(1.5)
    try:
        image_bytes = await asyncio.to_thread(_apply_filter)
    except GenerationError:
        raise
    except Exception as exc:
        raise GenerationError(f"Mock generation thread failed: {exc}") from exc

    logger.info("Mock generation complete, result_size=%s bytes", len(image_bytes))
    return GenerationResult(
        image_bytes=image_bytes,
        content_type="image/jpeg",
        cost_usd=0.0,
        prompt_used=f"[MOCK] {prompt_template}",
        provider_used="mock",
    )


# ── Hugging Face Provider ────────────────────────────────────────────

async def _generate_with_huggingface(
    selfie_bytes: bytes, prompt_template: str
) -> GenerationResult:
    """Generate using Hugging Face Serverless Inference API.

    Supports both text-to-image and image-to-image models.
    Retries on cold starts (503) and transient failures (429, 5xx, timeouts).
    """
    headers = {"Authorization": f"Bearer {settings.huggingface_api_key}"}
    model_name = settings.huggingface_model
    api_url = f"https://api-inference.huggingface.co/models/{model_name}"

    # Detect if this is an image-to-image model
    is_img2img = any(
        x in model_name.lower()
        for x in ["img2img", "image-to-image", "controlnet", "ip-adapter", "inpainting"]
    )

    started = time.monotonic()
    logger.info(
        "HF generation started: model=%s, mode=%s, selfie_size=%s bytes",
        model_name,
        "img2img" if is_img2img else "text-to-image",
        len(selfie_bytes),
    )

    async def _make_request():
        """Make a single request to Hugging Face."""
        async with httpx.AsyncClient(timeout=120) as client:
            if is_img2img:
                # Image-to-image: encode selfie as base64 and include in JSON
                b64_image = base64.b64encode(selfie_bytes).decode("utf-8")
                payload = {
                    "prompt": prompt_template,
                    "image": f"data:image/jpeg;base64,{b64_image}",
                }
                logger.debug("Sending img2img request to HF")
                resp = await client.post(api_url, headers=headers, json=payload)
            else:
                # Text-to-image: prompt only
                payload = {"inputs": prompt_template}
                logger.debug("Sending text-to-image request to HF")
                resp = await client.post(api_url, headers=headers, json=payload)

            return resp

    # Retry loop with special handling for 503 (cold start)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = await _make_request()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < max_retries:
                delay = min(_RETRY_BASE_DELAY * (2 ** (attempt - 1)), _RETRY_MAX_DELAY)
                logger.warning(
                    f"HF network error on attempt {attempt}/{max_retries}: {exc}. "
                    f"Retrying in {delay:.1f}s..."
                )
                await asyncio.sleep(delay)
                continue
            raise GenerationError(
                f"HF network error after {max_retries} attempts: {exc}"
            ) from exc

        # Handle 503 Model Cold Start
        if resp.status_code == 503:
            try:
                error_data = resp.json()
                est_time = float(error_data.get("estimated_time", 15.0))
            except (ValueError, TypeError, KeyError):
                est_time = 15.0

            wait_sec = min(max(est_time, 5.0), 30.0)
            logger.warning(
                f"HF model cold-starting (attempt {attempt}/{max_retries}). "
                f"Waiting {wait_sec:.1f}s..."
            )
            if attempt < max_retries:
                await asyncio.sleep(wait_sec)
                continue

            raise GenerationError(
                f"HF model failed to start after {max_retries} cold-start attempts"
            )

        # Handle other HTTP errors
        if resp.status_code != 200:
            error_detail = resp.text
            try:
                error_detail = resp.json().get("error", resp.text)
            except Exception:
                pass
            raise GenerationError(
                f"HF API error (status {resp.status_code}): {error_detail}"
            )

        # Success
        image_bytes = resp.content
        break

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "HF generation complete in %sms, result_size=%s bytes",
        elapsed_ms,
        len(image_bytes),
    )

    return GenerationResult(
        image_bytes=image_bytes,
        content_type="image/jpeg",
        cost_usd=0.0,  # Hugging Face free tier
        prompt_used=prompt_template,
        provider_used="huggingface",
    )