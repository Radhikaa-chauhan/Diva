"""Auto-draft a reference's hidden prompt from an uploaded image, via Gemini vision.

Free tier: Google AI Studio key (GEMINI_API_KEY). Only used by the admin
"auto-write from image" button — low volume, so cost/limits never bite.
"""
import base64
import json
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Same structured brief as the curate CLI; describe the scene/style, never the person.
VISION_PROMPT = (
    "Describe this photo as a structured photography brief for recreating its "
    "style with a DIFFERENT person. Return JSON only (no markdown), with fields: "
    "shot_type, lighting, mood, setting, pose_and_expression, wardrobe_style, "
    "color_grade, notable_elements. Do not describe the specific person — only "
    "the scene, style, lighting, and composition."
)


class CurationError(Exception):
    """Raised when auto-drafting a prompt fails."""


def build_prompt_template(style: dict) -> str:
    """Turn a style brief into an image-to-image prompt that preserves identity."""
    notable = style.get("notable_elements") or ""
    notable_clause = f" {notable}." if notable else ""
    return (
        f"Place this person in {style.get('setting', 'the scene')}, with "
        f"{style.get('lighting', 'natural')} lighting and a {style.get('mood', 'neutral')} mood. "
        f"Camera framing: {style.get('shot_type', 'portrait')}. "
        f"Wardrobe: adapt to {style.get('wardrobe_style', 'the reference')}.{notable_clause} "
        "Keep the person's face, identity, proportions, and expression consistent with the "
        "reference selfie — change only the scene, lighting, and styling around them."
    )


def _extract_json(text: str) -> dict:
    """Gemini sometimes wraps JSON in ```json fences — strip and parse."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1]
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t.strip())


async def draft_from_image(image_bytes: bytes, mime_type: str) -> dict:
    """Return {"style_description": {...}, "prompt_template": "..."} for an image."""
    key = settings.gemini_api_key
    if not key:
        raise CurationError("GEMINI_API_KEY is not configured — set it to use auto-write.")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent?key={key}"
    )
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}},
                {"text": VISION_PROMPT},
            ]
        }],
        "generationConfig": {"response_mime_type": "application/json"},
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        raise CurationError(f"Gemini request failed: {exc}") from exc

    if resp.status_code != 200:
        raise CurationError(f"Gemini API error (status {resp.status_code}): {resp.text[:200]}")

    try:
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        style = _extract_json(text)
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise CurationError(f"Could not parse Gemini response: {exc}") from exc

    return {"style_description": style, "prompt_template": build_prompt_template(style)}
