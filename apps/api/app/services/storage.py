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


def delete_file(url: str) -> bool:
    """Delete a file by its public URL. Returns True if deleted, False if not found."""
    try:
        key = url.split("/storage/", 1)[1]
        path = settings.storage_dir / key
        if path.exists():
            path.unlink()
            return True
    except (IndexError, OSError):
        pass
    return False


def get_file_size(url: str) -> int:
    """Return file size in bytes for a stored file. Returns 0 if not found."""
    try:
        key = url.split("/storage/", 1)[1]
        path = settings.storage_dir / key
        if path.exists():
            return path.stat().st_size
    except (IndexError, OSError):
        pass
    return 0