"""Seeds a handful of placeholder reference_photos so the library isn't
empty during local development.

These are NOT real curated presets — the thumbnails are locally-generated
placeholder graphics, not AI-generated images from a reviewed prompt
template (see ADR-3 / curate.py for the real pipeline). Swap these out
with real presets from `python -m app.curate` before showing this to
anyone outside your own dev loop.

Run: python -m app.seed
"""
import io

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models.reference_photo import ReferencePhoto
from app.services import storage

PLACEHOLDER_PRESETS = [
    {
        "title": "Golden Hour Portrait",
        "collection": "Editorial",
        "color": (212, 148, 74),
        "style_description": {
            "shot_type": "close-up portrait, shallow depth of field",
            "lighting": "warm golden-hour backlight with soft rim light",
            "mood": "wistful, cinematic",
            "setting": "open field at sunset",
            "pose_and_expression": "three-quarter turn, soft gaze off-camera",
            "wardrobe_style": "flowing neutral-tone fabric",
            "color_grade": "warm amber highlights, deep shadows",
            "notable_elements": "sun flare in frame",
        },
        "prompt_template": (
            "Place this person in an open field at golden hour, with warm backlit "
            "sunset lighting and a wistful, cinematic mood. Camera framing: close-up "
            "portrait, shallow depth of field. Wardrobe: adapt to flowing neutral-tone "
            "fabric. Include a subtle sun flare in frame. Keep the person's face, "
            "identity, proportions, and expression consistent with the reference selfie "
            "— change only the scene, lighting, and styling around them."
        ),
    },
    {
        "title": "Moody Studio Noir",
        "collection": "Editorial",
        "color": (40, 40, 48),
        "style_description": {
            "shot_type": "medium shot, high contrast",
            "lighting": "single hard side-light, deep shadow",
            "mood": "moody, dramatic",
            "setting": "plain dark studio backdrop",
            "pose_and_expression": "direct gaze, neutral expression",
            "wardrobe_style": "dark tailored clothing",
            "color_grade": "desaturated, high contrast black and white",
            "notable_elements": "visible film grain",
        },
        "prompt_template": (
            "Place this person against a plain dark studio backdrop, lit with a single "
            "hard side-light and deep shadow for a moody, dramatic mood. Camera framing: "
            "medium shot, high contrast. Wardrobe: adapt to dark tailored clothing. "
            "Render in a desaturated, high-contrast black and white grade with visible "
            "film grain. Keep the person's face, identity, proportions, and expression "
            "consistent with the reference selfie — change only the scene, lighting, and "
            "styling around them."
        ),
    },
    {
        "title": "Cinematic Neon Street",
        "collection": "Cinematic",
        "color": (98, 60, 158),
        "style_description": {
            "shot_type": "wide-ish medium shot",
            "lighting": "colored neon signage, blue/magenta glow",
            "mood": "cinematic, nocturnal energy",
            "setting": "rain-slicked city street at night",
            "pose_and_expression": "walking, confident half-glance",
            "wardrobe_style": "modern streetwear",
            "color_grade": "teal-and-magenta cinematic grade",
            "notable_elements": "reflections in wet pavement",
        },
        "prompt_template": (
            "Place this person on a rain-slicked city street at night, lit by colored "
            "neon signage casting a blue/magenta glow, for a cinematic, nocturnal-energy "
            "mood. Camera framing: wide-ish medium shot. Wardrobe: adapt to modern "
            "streetwear. Include reflections in the wet pavement. Grade in a teal-and-"
            "magenta cinematic look. Keep the person's face, identity, proportions, and "
            "expression consistent with the reference selfie — change only the scene, "
            "lighting, and styling around them."
        ),
    },
    {
        "title": "Soft Editorial Daylight",
        "collection": "Editorial",
        "color": (222, 200, 176),
        "style_description": {
            "shot_type": "close-up, soft focus background",
            "lighting": "diffused natural window light",
            "mood": "calm, airy",
            "setting": "minimal bright interior",
            "pose_and_expression": "relaxed, slight smile",
            "wardrobe_style": "soft neutral knitwear",
            "color_grade": "light and airy, low contrast",
            "notable_elements": "none",
        },
        "prompt_template": (
            "Place this person in a minimal, bright interior lit by diffused natural "
            "window light, for a calm, airy mood. Camera framing: close-up with a soft "
            "focus background. Wardrobe: adapt to soft neutral knitwear. Grade light and "
            "airy with low contrast. Keep the person's face, identity, proportions, and "
            "expression consistent with the reference selfie — change only the scene, "
            "lighting, and styling around them."
        ),
    },
    {
        "title": "Desert Cinematic Wide",
        "collection": "Cinematic",
        "color": (176, 108, 66),
        "style_description": {
            "shot_type": "medium-wide, cinematic aspect feel",
            "lighting": "harsh midday sun, strong shadow",
            "mood": "epic, sun-bleached",
            "setting": "open desert landscape",
            "pose_and_expression": "looking toward horizon",
            "wardrobe_style": "earth-tone travel wear",
            "color_grade": "sun-bleached, warm highlights",
            "notable_elements": "heat haze in distance",
        },
        "prompt_template": (
            "Place this person in an open desert landscape under harsh midday sun with "
            "strong shadow, for an epic, sun-bleached mood. Camera framing: medium-wide, "
            "cinematic aspect feel. Wardrobe: adapt to earth-tone travel wear. Include "
            "subtle heat haze in the distance. Grade sun-bleached with warm highlights. "
            "Keep the person's face, identity, proportions, and expression consistent "
            "with the reference selfie — change only the scene, lighting, and styling "
            "around them."
        ),
    },
    {
        "title": "Blue Hour City Balcony",
        "collection": "Cinematic",
        "color": (52, 74, 110),
        "style_description": {
            "shot_type": "medium shot",
            "lighting": "cool blue-hour ambient with warm window glow behind",
            "mood": "quiet, reflective",
            "setting": "city balcony at dusk",
            "pose_and_expression": "leaning on railing, looking away from camera",
            "wardrobe_style": "casual layered outerwear",
            "color_grade": "cool blues with warm accent lights",
            "notable_elements": "city skyline softly out of focus",
        },
        "prompt_template": (
            "Place this person on a city balcony at dusk, lit by cool blue-hour ambient "
            "light with warm window glow behind them, for a quiet, reflective mood. "
            "Camera framing: medium shot. Wardrobe: adapt to casual layered outerwear. "
            "Include a softly out-of-focus city skyline. Grade in cool blues with warm "
            "accent lights. Keep the person's face, identity, proportions, and expression "
            "consistent with the reference selfie — change only the scene, lighting, and "
            "styling around them."
        ),
    },
]


def _placeholder_thumbnail(title: str, color: tuple[int, int, int]) -> bytes:
    image = Image.new("RGB", (640, 800), color)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((40, 700), title, fill="white", font=font)
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing_titles = set(db.scalars(select(ReferencePhoto.title)).all())
        created = 0
        for preset in PLACEHOLDER_PRESETS:
            if preset["title"] in existing_titles:
                continue
            thumb_bytes = _placeholder_thumbnail(preset["title"], preset["color"])
            thumbnail_url = storage.save_bytes("thumbnails", "thumb.jpg", thumb_bytes)
            db.add(
                ReferencePhoto(
                    title=preset["title"],
                    collection=preset["collection"],
                    thumbnail_url=thumbnail_url,
                    style_description=preset["style_description"],
                    prompt_template=preset["prompt_template"],
                    active=True,
                )
            )
            created += 1
        db.commit()
        print(f"Seeded {created} new reference photo(s). Total presets available: {len(PLACEHOLDER_PRESETS)}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()