"""Local-disk object storage.

V1 dev implementation. TRD calls for an S3-compatible bucket in production —
swap this module's two functions for S3 puts/presigned-URL reads and nothing
else in the app needs to change, since callers only ever deal with
(relative key -> public URL).
"""
import uuid
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def save_bytes(subdir: str, filename_hint: str, data: bytes) -> str:
    ext = Path(filename_hint).suffix or ".jpg"
    key = f"{subdir}/{uuid.uuid4()}{ext}"
    dest = settings.storage_dir / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return url_for(key)


def url_for(key: str) -> str:
    return f"{settings.public_base_url}/storage/{key}"