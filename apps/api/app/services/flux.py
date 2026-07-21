"""Image generation adapter — Hugging Face Inference Providers.

`generate(selfie_bytes, prompt_template)` routes the user's selfie through an
image-to-image model, so the uploaded face actually influences the output.
Uses the official `huggingface_hub.InferenceClient`, which targets the current
Inference Providers router (the old api-inference.huggingface.co endpoint is
dead) and picks a working provider automatically.

Failure policy: fail loudly. The local sepia mock only runs when
ALLOW_MOCK_FALLBACK=true and the environment is development/test/local —
a failed generation must surface as a FAILED job, never a fake success.

Retries live in ONE place: job_runner's attempt loop. No retry here.
"""
import asyncio
import io
import logging
import time
from dataclasses import dataclass

from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

MAX_PROMPT_LENGTH = 1000

_MOCK_ENVIRONMENTS = {"development", "test", "local"}

# Lazy singleton — one client, one connection pool, reused across jobs.
_hf_client = None


@dataclass
class GenerationResult:
    image_bytes: bytes
    content_type: str
    cost_usd: float
    prompt_used: str
    provider_used: str  # "huggingface" or "mock"


class GenerationError(Exception):
    """Raised when image generation fails."""


class InputValidationError(GenerationError):
    """Raised when input validation fails."""


def _get_hf_client():
    global _hf_client
    if _hf_client is None:
        from huggingface_hub import InferenceClient

        _hf_client = InferenceClient(api_key=settings.huggingface_api_key)
    return _hf_client


def _validate_inputs(selfie_bytes: bytes, prompt_template: str) -> None:
    if not selfie_bytes:
        raise InputValidationError("Selfie image is empty.")

    max_bytes = settings.max_selfie_size_mb * 1024 * 1024
    if len(selfie_bytes) > max_bytes:
        raise InputValidationError(
            f"Selfie is {len(selfie_bytes)} bytes; max is {max_bytes} bytes."
        )

    if not prompt_template or not isinstance(prompt_template, str):
        raise InputValidationError("Prompt must be a non-empty string.")

    if len(prompt_template) > MAX_PROMPT_LENGTH:
        raise InputValidationError(
            f"Prompt is {len(prompt_template)} chars; max is {MAX_PROMPT_LENGTH}."
        )

    try:
        Image.open(io.BytesIO(selfie_bytes)).verify()
    except Exception as exc:
        raise InputValidationError(f"Selfie image is corrupted or unreadable: {exc}") from exc


async def generate(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    """Generate an image from a selfie and prompt. Raises GenerationError on failure."""
    _validate_inputs(selfie_bytes, prompt_template)

    mock_allowed = (
        settings.allow_mock_fallback and settings.environment in _MOCK_ENVIRONMENTS
    )

    if not settings.huggingface_api_key:
        if mock_allowed:
            logger.warning("HUGGINGFACE_API_KEY not set — using mock generator (dev only).")
            return await _generate_mock(selfie_bytes, prompt_template)
        raise GenerationError(
            "No image generation provider configured (set HUGGINGFACE_API_KEY)."
        )

    try:
        return await _generate_with_huggingface(selfie_bytes, prompt_template)
    except InputValidationError:
        raise
    except GenerationError as exc:
        if mock_allowed:
            logger.warning("HF generation failed (%s) — mock fallback (dev only).", exc)
            return await _generate_mock(selfie_bytes, prompt_template)
        raise


async def _generate_with_huggingface(
    selfie_bytes: bytes, prompt_template: str
) -> GenerationResult:
    """Image-to-image via HF Inference Providers: the selfie is the input image."""
    model = settings.huggingface_model
    started = time.monotonic()
    logger.info(
        "HF image-to-image started: model=%s, selfie_size=%s bytes", model, len(selfie_bytes)
    )

    def _call() -> bytes:
        image = _get_hf_client().image_to_image(
            image=selfie_bytes,
            prompt=prompt_template,
            model=model,
        )
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=92)
        return buf.getvalue()

    try:
        # Sync client in a thread — avoids the aiohttp dep of AsyncInferenceClient.
        image_bytes = await asyncio.to_thread(_call)
    except Exception as exc:
        raise GenerationError(f"Hugging Face generation failed: {exc}") from exc

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info("HF generation complete in %sms, result_size=%s bytes", elapsed_ms, len(image_bytes))

    return GenerationResult(
        image_bytes=image_bytes,
        content_type="image/jpeg",
        cost_usd=0.0,  # covered by HF free monthly inference credits
        prompt_used=prompt_template,
        provider_used="huggingface",
    )


async def _generate_mock(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    """Local PIL sepia filter for dev/test ($0). Never runs in production."""

    def _apply_filter() -> bytes:
        from PIL import ImageEnhance, ImageOps

        image = Image.open(io.BytesIO(selfie_bytes)).convert("RGB")
        image = ImageOps.exif_transpose(image)
        image = ImageOps.colorize(
            ImageOps.grayscale(image), black="#1a1024", white="#f4d9a0", mid="#b5673d"
        )
        image = ImageEnhance.Contrast(image).enhance(1.15)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    try:
        image_bytes = await asyncio.to_thread(_apply_filter)
    except Exception as exc:
        raise GenerationError(f"Mock generation failed: {exc}") from exc

    return GenerationResult(
        image_bytes=image_bytes,
        content_type="image/jpeg",
        cost_usd=0.0,
        prompt_used=f"[MOCK] {prompt_template}",
        provider_used="mock",
    )
