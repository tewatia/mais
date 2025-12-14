from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz", tags=["health"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
