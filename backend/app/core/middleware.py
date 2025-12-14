from __future__ import annotations

import logging
import time
import uuid

from app.core.logging import request_id_ctx
from fastapi import Request, Response

logger = logging.getLogger(__name__)


async def request_context_middleware(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_ctx.set(request_id)

    start = time.perf_counter()
    try:
        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "request completed",
            extra={
                "method": request.method,
                "path": str(request.url.path),
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )
        request_id_ctx.reset(token)
