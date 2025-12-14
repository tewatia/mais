from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

EventType = Literal["status", "token", "message", "error"]


@dataclass(frozen=True)
class SimulationEvent:
    type: EventType
    data: dict[str, Any]


def sse_encode(event: SimulationEvent) -> str:
    """
    Encode a single event as SSE text.
    """
    payload = json.dumps(event.data, ensure_ascii=False)
    return f"event: {event.type}\ndata: {payload}\n\n"
