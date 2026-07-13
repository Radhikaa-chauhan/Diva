from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "postgresql://postgres:postgres@localhost:5432/diva"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ── Storage ───────────────────────────────────────────────────────
    storage_dir: Path = BASE_DIR / "storage"
    public_base_url: str = "http://localhost:8000"

    # ── CORS ──────────────────────────────────────────────────────────
    allowed_origin: str = "http://localhost:3000"

    # ── JWT Auth ──────────────────────────────────────────────────────
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ── Image Generation ──────────────────────────────────────────────
    # When unset, generation falls back to a local mock so the whole
    # pipeline is runnable without any paid API keys.
    flux_api_key: str | None = None
    fal_flux_model: str = "fal-ai/flux-pro/kontext"
    huggingface_api_key: str | None = None
    huggingface_model: str = "black-forest-labs/FLUX.1-schnell"

    # ── Limits ────────────────────────────────────────────────────────
    max_selfie_size_mb: int = 10
    max_generation_attempts: int = 2
    rate_limit_per_hour: int = 20
    max_storage_per_user_mb: int = 500


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "selfies").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "results").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings