import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

# Default that is intentionally detectable as insecure so we can warn at
# startup — replaced by a real secret via the JWT_SECRET_KEY env var.
_INSECURE_DEFAULT_SECRET = "change-me-in-production-use-a-long-random-string"


def _sanitize_db_url(url: str) -> str:
    """Mask password in database URL for safe logging to prevent credential leaks."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunparse(parsed._replace(netloc=netloc))
        return url
    except Exception:
        return "postgresql://***@***"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Environment ───────────────────────────────────────────────────
    environment: str = "development"

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/diva"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Storage ───────────────────────────────────────────────────────
    storage_dir: Path = BASE_DIR / "storage"
    public_base_url: str = "http://localhost:8000"
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str = "us-east-1"
    aws_s3_bucket_name: str | None = None

    # ── CORS ──────────────────────────────────────────────────────────
    # Supports single origin or comma-separated origins (e.g., "http://localhost:3000,https://diva.com")
    allowed_origin: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse allowed_origin string into a list of clean origin URLs for CORS middleware."""
        if not self.allowed_origin:
            return ["http://localhost:3000"]
        return [origin.strip() for origin in self.allowed_origin.split(",") if origin.strip()]

    # ── JWT Auth ──────────────────────────────────────────────────────
    jwt_secret_key: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7
    email_token_expire_hours: int = 24
    password_reset_token_expire_minutes: int = 15

    # ── Rate Limiting ──────────────────────────────────────────────────
    login_rate_limit_requests: int = 5
    login_rate_limit_window_seconds: int = 900  # 15 minutes
    rate_limit_per_hour: int = 20  # Maximum image generation jobs per user per hour

    # ── Image Generation ──────────────────────────────────────────────
    # Hugging Face Inference Providers credentials (Primary).
    # Model must support image-to-image so the selfie is actually used.
    huggingface_api_key: str | None = None
    huggingface_model: str = "black-forest-labs/FLUX.1-Kontext-dev"
    # Dev-only escape hatch: sepia mock instead of a hard failure when the
    # provider is down/unconfigured. Ignored outside development/test/local.
    allow_mock_fallback: bool = False

    # ── Limits ────────────────────────────────────────────────────────
    max_selfie_size_mb: int = 10
    max_generation_attempts: int = 3  # Default 3 attempts for retries to function
    max_storage_per_user_mb: int = 500


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    # 1. Database URL & Pool Validation
    if not settings.database_url or not any(
        settings.database_url.startswith(prefix)
        for prefix in ("postgresql", "sqlite")
    ):
        raise ValueError(f"Invalid database_url protocol schema: {settings.database_url}")

    if settings.db_pool_size <= 0:
        raise ValueError("db_pool_size must be > 0")
    if settings.db_max_overflow < 0:
        raise ValueError("db_max_overflow must be >= 0")

    # 2. Storage Directory Validation & Writability Check
    try:
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        (settings.storage_dir / "selfies").mkdir(parents=True, exist_ok=True)
        (settings.storage_dir / "results").mkdir(parents=True, exist_ok=True)
        (settings.storage_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

        # Test write permission
        test_file = settings.storage_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except Exception as exc:
        raise RuntimeError(
            f"Storage directory is invalid or not writable: {settings.storage_dir} — {exc}"
        )

    # 3. Generation Retry & Limit Validation
    if settings.max_generation_attempts < 1:
        raise ValueError("max_generation_attempts must be >= 1 for retry logic to operate")

    if settings.max_selfie_size_mb <= 0:
        raise ValueError("max_selfie_size_mb must be > 0")

    if settings.rate_limit_per_hour <= 0:
        raise ValueError("rate_limit_per_hour must be > 0")

    # 4. Hugging Face Credentials & Model Format Validation
    if not settings.huggingface_api_key or settings.huggingface_api_key == "change-me":
        logger.warning(
            "HUGGINGFACE_API_KEY is not set or using placeholder. "
            "Image generation will run in fallback mock mode."
        )

    if not settings.huggingface_model or "/" not in settings.huggingface_model:
        raise ValueError(
            f"Invalid huggingface_model format (expected 'owner/model-name'): {settings.huggingface_model}"
        )

    # 5. JWT Auth & Expiration Validation
    if settings.jwt_secret_key == _INSECURE_DEFAULT_SECRET:
        logger.warning(
            "JWT_SECRET_KEY is using the insecure default. "
            "Set a strong random secret (64+ chars) before deploying to production."
        )

    if settings.jwt_secret_key and len(settings.jwt_secret_key) < 32:
        logger.warning(
            "JWT_SECRET_KEY is shorter than 32 characters. "
            "Use a longer secret for production security."
        )

    valid_jwt_algos = {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512"}
    if settings.jwt_algorithm not in valid_jwt_algos:
        raise ValueError(
            f"Unsupported jwt_algorithm: {settings.jwt_algorithm}. Supported: {valid_jwt_algos}"
        )

    if settings.access_token_expire_minutes <= 0:
        raise ValueError("access_token_expire_minutes must be > 0")
    if settings.refresh_token_expire_days <= 0:
        raise ValueError("refresh_token_expire_days must be > 0")
    if settings.email_token_expire_hours <= 0:
        raise ValueError("email_token_expire_hours must be > 0")
    if settings.password_reset_token_expire_minutes <= 0:
        raise ValueError("password_reset_token_expire_minutes must be > 0")

    # Log sanitized settings without leaking DB password
    logger.info(
        "Settings loaded successfully — storage_dir=%s, db=%s",
        settings.storage_dir,
        _sanitize_db_url(settings.database_url),
    )
    return settings