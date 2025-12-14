from __future__ import annotations

import asyncio
import logging
import uuid

from app.core.config import Settings
from app.simulations.events import SimulationEvent
from app.simulations.models import StartSimulationRequest
from app.simulations.state import SimulationState

logger = logging.getLogger(__name__)


class SimulationManager:
    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._sims: dict[str, SimulationState] = {}

    def create(self, req: StartSimulationRequest) -> SimulationState:
        simulation_id = str(uuid.uuid4())
        state = SimulationState(simulation_id=simulation_id, request=req)
        self._sims[simulation_id] = state
        return state

    def get(self, simulation_id: str) -> SimulationState | None:
        return self._sims.get(simulation_id)

    def has_active(self) -> bool:
        # Only one active simulation at a time.
        for st in self._sims.values():
            if st.task is not None and not st.finished_event.is_set():
                return True
        return False

    async def start(self, state: SimulationState) -> None:
        if state.task is not None:
            return

        async def _runner():
            try:
                from app.simulations.runner import run_simulation

                await run_simulation(state=state, settings=self._settings)
            except asyncio.CancelledError:
                # Stop was requested; surface "stopped" and end cleanly.
                state.cancel_event.set()
                await asyncio.shield(
                    state.publish(
                        SimulationEvent(type="status", data={"status": "stopped"})
                    )
                )
                return
            except Exception:
                logger.exception(
                    "simulation runner crashed",
                    extra={"simulation_id": state.simulation_id},
                )
                await state.publish(
                    SimulationEvent(
                        type="error",
                        data={"message": "Simulation crashed unexpectedly."},
                    )
                )
            finally:
                state.finished_event.set()

        state.task = asyncio.create_task(
            _runner(), name=f"simulation:{state.simulation_id}"
        )

    async def stop(self, simulation_id: str) -> bool:
        state = self._sims.get(simulation_id)
        if state is None:
            return False
        state.cancel_event.set()
        await state.publish(SimulationEvent(type="status", data={"status": "stopping"}))
        if state.task is not None and not state.task.done():
            state.task.cancel()
        return True
