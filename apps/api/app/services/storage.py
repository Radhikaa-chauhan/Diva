"""Local and AWS S3 object storage service.

Features:
- Robust path-traversal prevention (Path.relative_to)
- Reusable, thread-safe S3 client with exponential retry configuration
- Atomic local file writes (temp file + atomic replace)
- File size limit checks to prevent DoS attacks
- Dynamic MIME type detection via mimetypes
- Robust S3 key extraction with URL unquoting (urllib.parse.unquote)
- Configurable S3 presigned URL expiration
- Detailed decision and audit logging
"""
import io
import os
import logging
import mimetypes
import tempfile
import urllib.parse
import uuid
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Constants
MAX_FILE_SIZE_BYTES = getattr(settings, "max_selfie_size_mb", 50) * 1024 * 1024
DEFAULT_PRESIGNED_EXPIRY_SECONDS = 604800  # 7 days

# Cached S3 Client Singleton
_s3_client = None


def _get_s3_client():
    """Get or initialize a cached S3 client with retry configuration."""
    global _s3_client

    if not settings.aws_s3_bucket_name:
        return None

    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        logger.warning("AWS S3 bucket configured but AWS credentials missing")
        return None

    if _s3_client is not None:
        return _s3_client

    try:
        import boto3
        from botocore.config import Config

        # Configure standard retries (3 attempts with exponential backoff)
        boto_config = Config(
            retries={"max_attempts": 3, "mode": "standard"},
            connect_timeout=5,
            read_timeout=10,
        )

        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
            config=boto_config,
        )
        logger.info("Initialized AWS S3 client for bucket=%s", settings.aws_s3_bucket_name)
        return _s3_client
    except Exception as exc:
        logger.error("Failed to initialize AWS S3 client: %s", exc)
        return None


def _resolve_safe_path(url: str) -> Optional[Path]:
    """Extract storage key from a local storage URL and resolve to a safe filesystem path.
    
    Uses Path.relative_to for strict path-traversal prevention.
    """
    if not url or "/storage/" not in url:
        return None

    try:
        key = url.split("/storage/", 1)[1]
    except IndexError:
        logger.warning("Could not extract storage key from url=%s", url)
        return None

    # Unquote URL-encoded keys
    key = urllib.parse.unquote(key)
    storage_root = settings.storage_dir.resolve()
    resolved = (settings.storage_dir / key).resolve()

    try:
        resolved.relative_to(storage_root)
    except ValueError:
        logger.error("Path traversal attempt blocked: url=%s resolved to %s outside root %s", url, resolved, storage_root)
        return None

    return resolved


def extract_s3_key(url: str) -> Optional[str]:
    """Extract clean, URL-decoded S3 key from any S3 URL format or presigned S3 URL."""
    if not url or ".amazonaws.com/" not in url:
        return None

    try:
        # Extract path component after .amazonaws.com/
        key_part = url.split(".amazonaws.com/", 1)[1]
        # Remove query parameters (e.g. presigned signature query string)
        raw_key = key_part.split("?", 1)[0]
        # URL decode special characters
        return urllib.parse.unquote(raw_key)
    except Exception as exc:
        logger.warning("Failed to extract S3 key from url=%s: %s", url, exc)
        return None


def save_bytes(subdir: str, filename_hint: str, data: bytes) -> str:
    """Save raw bytes to S3 object storage or local disk with atomic writes and size checks."""
    if not data:
        raise ValueError("Cannot save empty file data")

    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File size ({len(data)} bytes) exceeds maximum limit ({MAX_FILE_SIZE_BYTES} bytes)"
        )

    # Determine extension and MIME content-type dynamically
    ext = Path(filename_hint).suffix.lower() or ".jpg"
    mime_type, _ = mimetypes.guess_type(filename_hint)
    if not mime_type:
        mime_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "application/octet-stream"

    key = f"{subdir.strip('/')}/{uuid.uuid4()}{ext}"

    # 1. Try AWS S3 upload
    s3_client = _get_s3_client()
    if s3_client:
        try:
            logger.info("Uploading object to S3: bucket=%s, key=%s, size=%d bytes", settings.aws_s3_bucket_name, key, len(data))
            s3_client.put_object(
                Bucket=settings.aws_s3_bucket_name,
                Key=key,
                Body=data,
                ContentType=mime_type,
            )
            s3_url = url_for(key)
            logger.info("Successfully uploaded object to S3: key=%s, url=%s", key, s3_url)
            return s3_url
        except Exception as exc:
            logger.error("AWS S3 upload failed (falling back to local storage): key=%s, error=%s", key, exc)

    # 2. Local storage fallback (atomic file write)
    storage_root = settings.storage_dir.resolve()
    dest = (storage_root / key).resolve()

    try:
        dest.relative_to(storage_root)
    except ValueError:
        raise PermissionError(f"Access denied for storage key: {key}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Write atomically via temp file in target directory then replace
    temp_fd, temp_path_str = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp_")
    try:
        with os.fdopen(temp_fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Atomic replace
        os.replace(temp_path_str, str(dest))
    except Exception as exc:
        if os.path.exists(temp_path_str):
            try:
                os.unlink(temp_path_str)
            except OSError:
                pass
        logger.error("Atomic local file write failed for key=%s: %s", key, exc)
        raise IOError(f"Failed to write file locally: {exc}") from exc

    result_url = url_for(key)
    logger.info("File saved atomically to local storage: key=%s, size=%d bytes, url=%s", key, len(data), result_url)
    return result_url


def url_for(key: str, expiry_seconds: int = DEFAULT_PRESIGNED_EXPIRY_SECONDS) -> str:
    """Generate public URL or presigned S3 URL for a given storage key."""
    s3_client = _get_s3_client()
    if s3_client:
        try:
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.aws_s3_bucket_name, "Key": key},
                ExpiresIn=expiry_seconds,
            )
        except Exception as exc:
            logger.error("Failed to generate presigned S3 URL for key=%s: %s", key, exc)
            return f"https://{settings.aws_s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{key}"

    return f"{settings.public_base_url}/storage/{key}"


def delete_file(url: str) -> bool:
    """Delete a file by its public URL (supports S3 and local storage)."""
    if not url:
        return False

    # S3 deletion
    s3_key = extract_s3_key(url)
    if s3_key and settings.aws_s3_bucket_name:
        s3_client = _get_s3_client()
        if s3_client:
            try:
                s3_client.delete_object(Bucket=settings.aws_s3_bucket_name, Key=s3_key)
                logger.info("File deleted from AWS S3: key=%s", s3_key)
                return True
            except Exception as exc:
                logger.error("Failed to delete file from AWS S3: key=%s, error=%s", s3_key, exc)
                return False

    # Local storage deletion
    path = _resolve_safe_path(url)
    if path is None:
        logger.warning("Delete request failed: Invalid path or path traversal attempt for url=%s", url)
        return False

    try:
        if path.exists():
            path.unlink()
            logger.info("File deleted from local storage: path=%s", path)
            return True
        else:
            logger.debug("File does not exist for delete request: path=%s", path)
            return False
    except OSError as exc:
        logger.error("Failed to delete file path=%s: %s", path, exc)
        return False


def get_file_size(url: str) -> int:
    """Return file size in bytes for a local stored file. Returns 0 if not found."""
    path = _resolve_safe_path(url)
    if path is None:
        return 0
    try:
        if path.exists():
            size = path.stat().st_size
            logger.debug("File size check: path=%s, size_bytes=%d", path, size)
            return size
    except OSError as exc:
        logger.error("Failed to stat file path=%s: %s", path, exc)
    return 0