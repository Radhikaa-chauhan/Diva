from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'app.db'}"
    storage_dir: Path = BASE_DIR / "storage"
    allowed_origin: str = "http://localhost:3000"

    # When unset, generation falls back to a local mock so the whole
    # pipeline is runnable without any paid API keys.
    flux_api_key: str | None = None
    fal_flux_model: str = "fal-ai/flux-pro/kontext"

    max_selfie_size_mb: int = 10
    max_generation_attempts: int = 2

    public_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "selfies").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "results").mkdir(parents=True, exist_ok=True)
    (settings.storage_dir / "thumbnails").mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    return settings