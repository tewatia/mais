from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from app.core.config import Settings, get_settings
from app.simulations.events import SimulationEvent, sse_encode
from app.simulations.manager import SimulationManager
from app.simulations.models import SimulationStartedResponse, StartSimulationRequest
from app.simulations.state import SimulationState
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def get_manager(request: Request) -> SimulationManager:
    return request.app.state.sim_manager


@router.post("/simulations", response_model=SimulationStartedResponse)
async def start_simulation(
    body: StartSimulationRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    manager: SimulationManager = Depends(get_manager),
) -> SimulationStartedResponse:
    # Server-side bounds (defense-in-depth beyond Pydantic)
    if body.turn_limit > settings.max_turn_limit:
        raise HTTPException(status_code=400, detail="turn_limit too large")

    if manager.has_active():
        raise HTTPException(
            status_code=409,
            detail="A simulation is already running. Stop it before starting a new one.",
        )

    state = manager.create(body)
    await manager.start(state)
    # logger.info("simulation started", extra={"simulation_id": state.simulation_id})
    logger.info(f"simulation started: {state.simulation_id}")
    return SimulationStartedResponse(simulation_id=state.simulation_id)


def _require_simulation(
    manager: SimulationManager, simulation_id: str
) -> SimulationState:
    state = manager.get(simulation_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Simulation not found.")
    return state


@router.get("/simulations/{simulation_id}/events", response_class=StreamingResponse)
async def stream_simulation_events(
    simulation_id: str,
    request: Request,
    manager: SimulationManager = Depends(get_manager),
) -> StreamingResponse:
    state = _require_simulation(manager, simulation_id)

    q = state.subscribe()

    async def gen() -> AsyncIterator[bytes]:
        try:
            # initial "connected" event
            yield sse_encode(
                SimulationEvent(type="status", data={"status": "connected"})
            ).encode("utf-8")
            while True:
                if await request.is_disconnected():
                    return

                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield sse_encode(event).encode("utf-8")
                except asyncio.TimeoutError:
                    # keepalive comment
                    yield b": keepalive\n\n"

                if state.finished_event.is_set() and q.empty():
                    return
        finally:
            state.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/simulations/{simulation_id}/stop")
async def stop_simulation(
    simulation_id: str,
    manager: SimulationManager = Depends(get_manager),
) -> dict[str, str]:
    ok = await manager.stop(simulation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Simulation not found.")
    return {"status": "ok"}


@router.get("/simulations/{simulation_id}/download")
async def download_transcript(
    simulation_id: str,
    manager: SimulationManager = Depends(get_manager),
) -> dict:
    state = _require_simulation(manager, simulation_id)

    if state.transcript is None:
        raise HTTPException(status_code=409, detail="Transcript not available yet.")

    return {
        "simulation_id": state.simulation_id,
        "topic": state.request.topic,
        "mode": state.request.mode,
        "stage": state.request.stage,
        "agents": [a.model_dump() for a in state.request.agents],
        "moderator": state.request.moderator.model_dump(),
        "synthesizer": state.request.synthesizer.model_dump(),
        "messages": [
            {"name": m.name, "content": m.content} for m in state.transcript.messages
        ],
    }
