from __future__ import annotations

from app.simulations.events import SimulationEvent, sse_encode


def test_sse_encode():
    event = SimulationEvent(type="status", data={"status": "started"})
    encoded = sse_encode(event)
    assert "event: status" in encoded
    assert "data:" in encoded
    assert encoded.endswith("\n\n")
