from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


def _dotenv_override_enabled() -> bool:
    v = os.getenv("DOTENV_OVERRIDE", "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def load_env_files(*, repo_root: Path | None = None) -> list[Path]:
    """
    Load environment variables from local env files using python-dotenv.

    - This is meant for local development convenience.
    - By default OS environment variables are NOT overridden.
      Set DOTENV_OVERRIDE=true to force `.env` to override existing env vars.
    - Returns a list of env file paths that were found and loaded.
    """
    root = repo_root or Path(__file__).resolve().parents[3]
    candidates = [
        root / "backend" / ".env",  # conventional
        root / "backend" / "env",  # non-dotfile fallback
    ]

    loaded: list[Path] = []
    for p in candidates:
        if p.exists() and p.is_file():
            load_dotenv(dotenv_path=p, override=_dotenv_override_enabled())
            loaded.append(p)
    return loaded


class Settings(BaseSettings):
    # Config is sourced from:
    # 1) python-dotenv loaded env vars (see load_env_files)
    # 2) OS environment variables
    model_config = SettingsConfigDict(extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    allowed_origins: str = "http://localhost:5173"

    max_turn_limit: int = 40
    max_agents: int = 4
    orphan_grace_seconds: int = 5

    # Model catalog configuration (optional override).
    # If empty, the server uses backend/model_catalog.json (or MODEL_CATALOG_PATH env var).
    models_catalog_path: str | None = None

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Ensure local env files are loaded before instantiating Settings.
    load_env_files()
    return Settings()
