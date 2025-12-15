from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure `backend/` is on sys.path so `import app.*` works when running tests from repo root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture()
def app():
    # ensure fresh settings per test session
    get_settings.cache_clear()
    # Ensure test environment settings (avoid orphan-cancel interfering with tests).
    os.environ["ENV"] = "test"
    os.environ["ORPHAN_GRACE_SECONDS"] = "0"
    return create_app()
