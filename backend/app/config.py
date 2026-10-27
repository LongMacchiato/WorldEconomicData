import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_BASE_URL = "https://api.db.nomics.world/v22"
DEFAULT_PROVIDERS_PAGE_LIMIT = 200
DEFAULT_DATASETS_PAGE_LIMIT = 100
DEFAULT_SERIES_PAGE_LIMIT = 50
MAX_SERIES_PAGE_LIMIT = 200
MAX_SELECTED_SERIES = 10


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DBNOMICS_BROWSER_",
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        extra="ignore",
        case_sensitive=False,
    )

    # Vite falls through ports when 5173 is already taken (e.g. 5174).
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    )
    api_base_url: str = DEFAULT_API_BASE_URL
    metadata_cache_max_size: int = 128
    metadata_cache_ttl_seconds: int = 900
    preview_default_page_size: int = 100
    preview_max_page_size: int = 1_000
    export_max_rows: int = 100_000
    max_selected_series: int = MAX_SELECTED_SERIES
    providers_page_limit: int = DEFAULT_PROVIDERS_PAGE_LIMIT
    datasets_page_limit: int = DEFAULT_DATASETS_PAGE_LIMIT
    series_page_limit: int = DEFAULT_SERIES_PAGE_LIMIT
    series_max_page_limit: int = MAX_SERIES_PAGE_LIMIT
    upstream_timeout_seconds: float = 60.0
    analytics_db_path: str = str(PROJECT_ROOT / "data" / "analytics.duckdb")
    analytics_max_query_rows: int = 5_000
    gemini_api_key: str | None = Field(
        default_factory=lambda: (
            os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        ),
        validation_alias=AliasChoices(
            "gemini_api_key",
            "DBNOMICS_BROWSER_GEMINI_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ),
    )
    gemini_model: str = "gemini-3.8-flash"
    fred_api_key: str | None = Field(
        default_factory=lambda: os.environ.get("FRED_API_KEY"),
        validation_alias=AliasChoices(
            "fred_api_key",
            "DBNOMICS_BROWSER_FRED_API_KEY",
            "FRED_API_KEY",
        ),
    )
    mlx_model_id: str = "mlx-community/Meta-Llama-3.1-8B-Instruct-4bit"
    hf_cache_dir: str = Field(
        default_factory=lambda: os.path.expanduser("~/.cache/huggingface")
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
