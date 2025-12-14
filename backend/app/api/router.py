from __future__ import annotations

from app.api.health import router as health_router
from app.api.models import router as models_router
from app.api.simulations import router as simulations_router
from fastapi import APIRouter

router = APIRouter()

router.include_router(health_router)
router.include_router(simulations_router, prefix="/api", tags=["simulations"])
router.include_router(models_router, prefix="/api", tags=["models"])
