from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def friendly_http_error(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": {"message": message}}
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception", extra={"path": str(request.url.path)})
    return friendly_http_error(500, "Unexpected server error. Please try again.")
