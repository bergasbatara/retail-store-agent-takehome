"""Application configuration loading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL_NAME = "gpt-5"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the retail agent process."""

    openai_api_key: str | None
    model_name: str
    db_path: Path
    seed_data_dir: Path
    log_level: str


def load_settings(project_root: Path | None = None) -> Settings:
    """Load runtime settings from the environment with local defaults."""
    root = project_root or discover_project_root()
    return Settings(
        openai_api_key=_read_optional_env("OPENAI_API_KEY"),
        model_name=os.getenv("RETAIL_AGENT_MODEL", DEFAULT_MODEL_NAME),
        db_path=_resolve_path(
            os.getenv("RETAIL_AGENT_DB_PATH"),
            default=root / ".retail_agent" / "store.db",
            root=root,
        ),
        seed_data_dir=_resolve_path(
            os.getenv("RETAIL_AGENT_SEED_DATA_DIR"),
            default=root / "data",
            root=root,
        ),
        log_level=os.getenv("RETAIL_AGENT_LOG_LEVEL", DEFAULT_LOG_LEVEL),
    )


def discover_project_root() -> Path:
    """Resolve the workspace root from the package location."""
    return Path(__file__).resolve().parents[2]


def _read_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _resolve_path(raw_value: str | None, *, default: Path, root: Path) -> Path:
    if not raw_value:
        return default.resolve()

    candidate = Path(raw_value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve()
