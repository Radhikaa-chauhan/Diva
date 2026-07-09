"""Selfie validation: file constraints + a real (if basic) local face-detection gate.

Uses OpenCV's bundled Haar cascade so this works fully offline with no API
key. It's a coarse, frontal-face detector — good enough to reject "no face
at all" uploads per TRD §12 without taking on a cloud vision dependency for
something this cheap to check locally. Swap for a hosted face API later if
the false-reject rate on angled/low-light selfies turns out to matter.
"""
import io

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import get_settings

settings = get_settings()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


class SelfieValidationError(Exception):
    pass


def validate_selfie(content_type: str, data: bytes) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise SelfieValidationError(f"Unsupported file type: {content_type}. Use JPEG, PNG, or WEBP.")

    max_bytes = settings.max_selfie_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise SelfieValidationError(f"File too large. Max size is {settings.max_selfie_size_mb}MB.")

    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except UnidentifiedImageError as exc:
        raise SelfieValidationError("File is not a readable image.") from exc

    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    if len(faces) == 0:
        raise SelfieValidationError("No face detected in the photo. Try a clearer, front-facing selfie.")