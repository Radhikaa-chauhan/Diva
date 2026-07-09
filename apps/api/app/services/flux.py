"""Image generation adapter.

Two backends behind one interface (`generate`):

- Mock (default, no FLUX_API_KEY set): applies a cheap local filter to the
  selfie so the full job pipeline — upload, poll, complete, download — is
  exercisable with zero cost and zero external calls. This is what "build
  functionality first" runs against.
- fal.ai Flux Kontext [pro] (TRD ADR-1): used automatically once
  FLUX_API_KEY is set. Talks to fal.ai's async queue API directly over
  httpx rather than pulling in the fal SDK, to keep the dependency surface
  small.

Swap points if you outgrow this: multi-provider fallback, streaming
progress instead of polling, FLUX.2 multi-selfie input (PRD P2).
"""
import asyncio
import io
import time
from dataclasses import dataclass

import httpx
from PIL import Image, ImageEnhance, ImageOps

from app.config import get_settings

settings = get_settings()

FAL_QUEUE_BASE = "https://queue.fal.run"


@dataclass
class GenerationResult:
    image_bytes: bytes
    content_type: str
    cost_usd: float
    prompt_used: str


class GenerationError(Exception):
    pass


async def generate(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    if settings.flux_api_key:
        return await _generate_with_fal(selfie_bytes, prompt_template)
    return await _generate_mock(selfie_bytes, prompt_template)


async def _generate_mock(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    def _apply_filter() -> bytes:
        image = Image.open(io.BytesIO(selfie_bytes)).convert("RGB")
        image = ImageOps.colorize(
            ImageOps.grayscale(image), black="#1a1024", white="#f4d9a0", mid="#b5673d"
        )
        image = ImageEnhance.Contrast(image).enhance(1.15)
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    await asyncio.sleep(1.5)  # simulate generation latency
    image_bytes = await asyncio.to_thread(_apply_filter)
    return GenerationResult(
        image_bytes=image_bytes,
        content_type="image/jpeg",
        cost_usd=0.0,
        prompt_used=f"[MOCK] {prompt_template}",
    )


async def _generate_with_fal(selfie_bytes: bytes, prompt_template: str) -> GenerationResult:
    headers = {"Authorization": f"Key {settings.flux_api_key}"}

    async with httpx.AsyncClient(timeout=60) as client:
        upload_resp = await client.post(
            "https://fal.run/storage/upload",
            headers=headers,
            files={"file": ("selfie.jpg", selfie_bytes, "image/jpeg")},
        )
        upload_resp.raise_for_status()
        selfie_url = upload_resp.json()["url"]

        submit_resp = await client.post(
            f"{FAL_QUEUE_BASE}/{settings.fal_flux_model}",
            headers=headers,
            json={"prompt": prompt_template, "image_url": selfie_url},
        )
        submit_resp.raise_for_status()
        submission = submit_resp.json()
        status_url = submission["status_url"]
        response_url = submission["response_url"]

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            status_resp = await client.get(status_url, headers=headers)
            status_resp.raise_for_status()
            status = status_resp.json().get("status")
            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR"):
                raise GenerationError(f"Flux generation failed with status {status}")
            await asyncio.sleep(1.5)
        else:
            raise GenerationError("Flux generation timed out")

        result_resp = await client.get(response_url, headers=headers)
        result_resp.raise_for_status()
        result_json = result_resp.json()
        image_url = result_json["images"][0]["url"]

        image_resp = await client.get(image_url)
        image_resp.raise_for_status()

    return GenerationResult(
        image_bytes=image_resp.content,
        content_type=image_resp.headers.get("content-type", "image/jpeg"),
        cost_usd=0.035,
        prompt_used=prompt_template,
    )