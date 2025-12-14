from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)


Provider = Literal["openai", "google", "anthropic"]


class ModelSpec(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    provider: Provider


class ModelCatalog(BaseModel):
    models: list[ModelSpec] = Field(default_factory=list)


def _backend_dir() -> Path:
    # backend/app/models/catalog.py -> backend/
    return Path(__file__).resolve().parents[2]


def default_catalog_path() -> Path:
    return _backend_dir() / "model_catalog.json"


def resolve_catalog_path(model_catalog_path: str | None) -> Path:
    """
    Resolution order:
    1) explicit argument
    2) env var MODEL_CATALOG_PATH
    3) backend/model_catalog.json
    """
    raw = (model_catalog_path or "").strip() or os.getenv("MODEL_CATALOG_PATH", "").strip()
    if raw:
        p = Path(raw)
        return p if p.is_absolute() else (_backend_dir() / p).resolve()
    return default_catalog_path()


def load_model_catalog(*, model_catalog_path: str | None = None) -> ModelCatalog:
    """
    Load the model catalog from disk.

    The intent is that this file can be changed without code changes (local dev),
    so we keep the implementation simple and read the file each time.
    """
    path = resolve_catalog_path(model_catalog_path)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return ModelCatalog.model_validate(data)
    except FileNotFoundError:
        logger.error("model catalog file not found", extra={"path": str(path)})
        return ModelCatalog(models=[])
    except (json.JSONDecodeError, ValidationError) as e:
        logger.exception(
            "invalid model catalog file",
            extra={"path": str(path), "error": str(e)},
        )
        return ModelCatalog(models=[])


