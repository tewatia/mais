from __future__ import annotations

from app.core.config import Settings, get_settings
from app.models.catalog import ModelCatalog, load_model_catalog
from fastapi import APIRouter, Depends

router = APIRouter()


@router.get("/models", response_model=ModelCatalog)
def list_models(settings: Settings = Depends(get_settings)) -> ModelCatalog:
    return load_model_catalog(model_catalog_path=settings.models_catalog_path)


