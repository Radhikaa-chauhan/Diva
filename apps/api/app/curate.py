"""Curation CLI (TRD §8, ROADMAP Phase 1).

Offline tool, run by you, not part of the deployed app's live request path.

    python -m app.curate path/to/inspiration.jpg

Flow:
  1. Sends the inspiration photo to Claude (vision) to draft a structured
     style_description + prompt_template. Requires ANTHROPIC_API_KEY.
  2. Prints the draft for you to review; you can edit prompt_template
     interactively before anything is saved.
  3. Generates a thumbnail from the *prompt_template* (via the same
     generate() adapter the live app uses) — never the original inspiration
     photo — per ADR-3, and saves the new preset to reference_photos.

The inspiration photo itself is never uploaded or stored (ADR-3 / TRD §10)
— it's read from your local disk and never leaves this process except as
input to the vision-analysis API call.
"""
import asyncio
import base64
import json
import logging
import os
import sys

import anthropic

from app.database import Base, SessionLocal, engine
from app.models.reference_photo import ReferencePhoto
from app.services import storage
from app.services.flux import generate

logger = logging.getLogger(__name__)

VISION_PROMPT = (
    "Describe this photo as a structured photography brief for someone "
    "recreating it with a different subject. Return JSON only, with fields: "
    "shot_type, lighting, mood, setting, pose_and_expression, wardrobe_style, "
    "color_grade, notable_elements. Do not describe the specific person in "
    "the photo — describe only the scene, style, and composition."
)


def _draft_from_inspiration(image_path: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Set ANTHROPIC_API_KEY to run vision analysis for curation.")

    logger.info("Reading inspiration image from %s", image_path)
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    logger.info("Inspiration image loaded: size_bytes=%s", len(image_bytes))

    media_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    client = anthropic.Anthropic(api_key=api_key)

    logger.info("Sending image to Claude vision API for analysis")
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": VISION_PROMPT},
                ],
            }
        ],
    )
    text = response.content[0].text
    logger.info("Claude vision API response received: %s chars", len(text))

    try:
        style = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Claude response as JSON: %s", exc)
        logger.error("Raw response: %s", text)
        raise SystemExit(
            f"Claude returned invalid JSON. Raw response:\n{text}"
        ) from exc

    return style


def _build_prompt_template(style: dict) -> str:
    notable = style.get("notable_elements") or ""
    notable_clause = f" {notable}." if notable else ""
    return (
        f"Place this person in {style['setting']}, with {style['lighting']} lighting "
        f"and a {style['mood']} mood. Camera framing: {style['shot_type']}. "
        f"Wardrobe: adapt to {style['wardrobe_style']}.{notable_clause} Keep the "
        "person's face, identity, proportions, and expression consistent with the "
        "reference selfie — change only the scene, lighting, and styling around them."
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m app.curate path/to/inspiration.jpg")

    image_path = sys.argv[1]
    logger.info("Curation started for image: %s", image_path)

    print("Analyzing inspiration photo...")
    style = _draft_from_inspiration(image_path)
    prompt_template = _build_prompt_template(style)

    print("\n--- Draft style_description ---")
    print(json.dumps(style, indent=2))
    print("\n--- Draft prompt_template ---")
    print(prompt_template)

    title = input("\nPreset title: ").strip()
    collection = input("Collection (optional): ").strip() or None
    edited = input("Press Enter to accept prompt_template above, or type a replacement: ").strip()
    if edited:
        prompt_template = edited

    print("Generating thumbnail from prompt_template (not from the inspiration photo)...")
    logger.info("Generating thumbnail for preset '%s'", title)

    async def _make_thumbnail() -> bytes:
        with open(image_path, "rb") as f:
            seed_bytes = f.read()
        result = await generate(seed_bytes, prompt_template)
        return result.image_bytes

    thumbnail_bytes = asyncio.run(_make_thumbnail())
    thumbnail_url = storage.save_bytes("thumbnails", "thumb.jpg", thumbnail_bytes)
    logger.info("Thumbnail saved at url=%s", thumbnail_url)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            ReferencePhoto(
                title=title,
                collection=collection,
                thumbnail_url=thumbnail_url,
                style_description=style,
                prompt_template=prompt_template,
                active=True,
            )
        )
        db.commit()
        logger.info("Preset '%s' saved to database", title)
    finally:
        db.close()

    print(f"\nSaved preset '{title}'. Thumbnail: {thumbnail_url}")


if __name__ == "__main__":
    main()