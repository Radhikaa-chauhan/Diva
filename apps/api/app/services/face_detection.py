"""Selfie validation: file constraints + a real (if basic) local face-detection gate.

Uses OpenCV's bundled Haar cascade so this works fully offline with no API
key. It's a coarse, frontal-face detector — good enough to reject "no face
at all" uploads per TRD §12 without taking on a cloud vision dependency for
something this cheap to check locally. Swap for a hosted face API later if
the false-reject rate on angled/low-light selfies turns out to matter.
"""
import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Guard against decompression bombs — reject images larger than 25 megapixels
_MAX_IMAGE_PIXELS = 25_000_000
Image.MAX_IMAGE_PIXELS = _MAX_IMAGE_PIXELS

_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


class SelfieValidationError(Exception):
    pass


def validate_selfie(content_type: str, data: bytes) -> None:
    logger.info("Validating selfie: content_type=%s, size_bytes=%s", content_type, len(data))

    if content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning("Unsupported content type: %s", content_type)
        raise SelfieValidationError(f"Unsupported file type: {content_type}. Use JPEG, PNG, or WEBP.")

    max_bytes = settings.max_selfie_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        logger.warning("File too large: %s bytes (max %s bytes)", len(data), max_bytes)
        raise SelfieValidationError(f"File too large. Max size is {settings.max_selfie_size_mb}MB.")

    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        logger.debug("Image verification passed: format=%s, size=%s", image.format, image.size)
        # Re-open after verify() since verify() can invalidate the image object
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except UnidentifiedImageError as exc:
        logger.warning("Unidentified image file")
        raise SelfieValidationError("File is not a readable image.") from exc
    except (SyntaxError, OSError, ValueError) as exc:
        logger.warning("Image open/verify failed: %s", exc)
        raise SelfieValidationError("File is corrupted or not a valid image.") from exc
    except Image.DecompressionBombError as exc:
        logger.error("Decompression bomb detected: %s", exc)
        raise SelfieValidationError("Image is too large (potential decompression bomb). Use a smaller image.") from exc

    logger.info("Running face detection on image size=%s", image.size)
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    faces = _cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    face_count = len(faces) if isinstance(faces, np.ndarray) else 0

    if face_count == 0:
        logger.warning("No face detected in selfie")
        raise SelfieValidationError("No face detected in the photo. Try a clearer, front-facing selfie.")

    logger.info("Face detection passed: faces_found=%s", face_count)