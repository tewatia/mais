from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.simulations.events import SimulationEvent
from app.simulations.models import SimulationTranscript, StartSimulationRequest


@dataclass
class SimulationState:
    simulation_id: str
    request: StartSimulationRequest
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    finished_event: asyncio.Event = field(default_factory=asyncio.Event)
    transcript: SimulationTranscript | None = None
    task: asyncio.Task | None = None
    subscribers: set[asyncio.Queue[SimulationEvent]] = field(default_factory=set)
    last_subscriber_change: float = field(default_factory=time.monotonic)

    def subscribe(self) -> asyncio.Queue[SimulationEvent]:
        q: asyncio.Queue[SimulationEvent] = asyncio.Queue()
        self.subscribers.add(q)
        self.last_subscriber_change = time.monotonic()
        return q

    def unsubscribe(self, q: asyncio.Queue[SimulationEvent]) -> None:
        self.subscribers.discard(q)
        self.last_subscriber_change = time.monotonic()
        # If nobody is listening anymore, stop the simulation to avoid burning tokens/cpu.
        if not self.subscribers and self.task is not None and not self.task.done():
            self.cancel_event.set()
            self.task.cancel()

    async def publish(self, event: SimulationEvent) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # No unbounded growth; drop when a subscriber is too slow.
                pass


