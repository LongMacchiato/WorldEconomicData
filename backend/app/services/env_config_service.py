"""Service for reading, masking, and persisting API keys in `.env`."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from app.config import PROJECT_ROOT, Settings
from app.domain.analytics_models import AiConfigStatus, AiConfigUpdateRequest

SUPPORTED_GEMINI_MODELS: frozenset[str] = frozenset(
    {
        "gemini-3.8-flash",
        "gemini-4-argon",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    }
)


def mask_secret(value: str | None) -> str | None:
    """Return a masked preview (`AIza...9xYz`) without exposing the full key.

    Args:
        value: Raw secret string or None.

    Returns:
        Masked preview string or None if empty.
    """
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    if len(cleaned) <= 8:
        return f"{cleaned[:2]}...{cleaned[-2:]}"
    return f"{cleaned[:4]}...{cleaned[-4:]}"


def get_ai_config_status(settings: Settings) -> AiConfigStatus:
    """Build the masked AiConfigStatus from active Settings.

    Args:
        settings: Active application Settings.

    Returns:
        AiConfigStatus with masked key previews.
    """
    gemini_masked = mask_secret(settings.gemini_api_key)
    fred_masked = mask_secret(settings.fred_api_key)
    return AiConfigStatus(
        gemini_key_configured=gemini_masked is not None,
        gemini_key_masked=gemini_masked,
        gemini_model=settings.gemini_model,
        fred_key_configured=fred_masked is not None,
        fred_key_masked=fred_masked,
    )


def update_env_config(
    request: AiConfigUpdateRequest,
    *,
    env_path: Path | None = None,
) -> None:
    """Persist updated API keys and model to `.env` and `os.environ`.

    Args:
        request: AiConfigUpdateRequest containing updated fields.
        env_path: Optional override path to `.env` for testing.
    """
    target_path = env_path or (PROJECT_ROOT / ".env")
    updates: dict[str, str] = {}

    if request.gemini_api_key is not None:
        cleaned_gemini = request.gemini_api_key.strip()
        updates["GEMINI_API_KEY"] = cleaned_gemini
        os.environ["GEMINI_API_KEY"] = cleaned_gemini

    if request.gemini_model is not None and request.gemini_model.strip():
        cleaned_model = request.gemini_model.strip()
        updates["DBNOMICS_BROWSER_GEMINI_MODEL"] = cleaned_model
        os.environ["DBNOMICS_BROWSER_GEMINI_MODEL"] = cleaned_model

    if request.fred_api_key is not None:
        cleaned_fred = request.fred_api_key.strip()
        updates["FRED_API_KEY"] = cleaned_fred
        os.environ["FRED_API_KEY"] = cleaned_fred

    if not updates:
        return

    _upsert_dotenv_lines(target_path, updates)


def _upsert_dotenv_lines(path: Path, updates: dict[str, str]) -> None:
    """Upsert key=value pairs in a `.env` file while preserving comments."""
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    remaining = dict(updates)
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)

    for key, val in remaining.items():
        new_lines.append(f"{key}={val}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        path.chmod(0o600)
