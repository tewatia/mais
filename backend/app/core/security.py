from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass
class _WindowCounter:
    window_start: float
    count: int


class SimpleRateLimiter:
    """
    Very small in-memory rate limiter to protect MVP endpoints.
    Not suitable for multi-instance deployments (needs shared store).
    """

    def __init__(self, max_requests: int = 120, window_seconds: int = 60) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._counters: dict[str, _WindowCounter] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        counter = self._counters.get(key)
        if counter is None or now - counter.window_start >= self._window_seconds:
            self._counters[key] = _WindowCounter(window_start=now, count=1)
            return True

        counter.count += 1
        return counter.count <= self._max_requests


_rate_limiter = SimpleRateLimiter()


async def simple_rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{request.url.path}"
    if not _rate_limiter.allow(key):
        logger.warning("rate limit exceeded", extra={"client_ip": client_ip, "path": str(request.url.path)})
        return JSONResponse(status_code=429, content={"error": {"message": "Too many requests. Slow down."}})
    return await call_next(request)


