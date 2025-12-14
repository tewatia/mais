from __future__ import annotations

import os
from pathlib import Path

from app.core.config import load_env_files


def test_load_env_files_loads_backend_dotenv(tmp_path: Path, monkeypatch):
    # Arrange a fake repo root with backend/.env
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    dotenv_path = backend_dir / ".env"
    dotenv_path.write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")

    # Make sure env isn't already set
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    # Act
    loaded = load_env_files(repo_root=tmp_path)

    # Assert
    assert dotenv_path in loaded
    assert os.environ.get("LOG_LEVEL") == "WARNING"


