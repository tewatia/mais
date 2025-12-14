from __future__ import annotations

import logging

from app.api.router import router as api_router
from app.core.config import get_settings
from app.core.errors import unhandled_exception_handler
from app.core.logging import configure_logging
from app.core.middleware import request_context_middleware
from app.core.security import simple_rate_limit_middleware
from app.simulations.manager import SimulationManager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="MAIS Backend", version="0.1.0")

    # Middleware: rate limiting -> request context/logging
    app.middleware("http")(simple_rate_limit_middleware)
    app.middleware("http")(request_context_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    app.add_exception_handler(Exception, unhandled_exception_handler)

    # In-memory manager (MVP). For multi-instance deployments, replace with shared store.
    app.state.sim_manager = SimulationManager(settings=settings)
    logger.info("app created")

    return app


app = create_app()
