from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx


class _FakeStreamingModel:
    def __init__(self, tokens: list[str]):
        self._tokens = tokens

    async def astream(self, _messages):
        for t in self._tokens:
            yield SimpleNamespace(content=t)


async def test_start_and_download_transcript(app, monkeypatch):
    # Patch the LLM factory used by the turn executor so we don't call real providers.
    from app.simulations import turn_executor

    def _fake_build_chat_model(
        *,
        settings,
        model,
        provider=None,
        temperature=None,
        max_tokens=None,
        context_size=None,
    ):  # noqa: ARG001
        # deterministic output per call
        return _FakeStreamingModel(tokens=[f"[{model}] hello "])

    monkeypatch.setattr(turn_executor, "build_chat_model", _fake_build_chat_model)

    payload = {
        "topic": "Is AI sentient?",
        "mode": "debate",
        "stage": "Mode: Debate Arena. Critique and disagree when appropriate.",
        "turn_limit": 1,  # 1 round with 2 agents = 2 messages
        "agents": [
            {
                "name": "Agent A",
                "model": "gpt-4o-mini",
                "system_prompt": "Be concise.",
                "provider": "openai",
            },
            {
                "name": "Agent B",
                "model": "claude-3-sonnet",
                "system_prompt": "Be skeptical.",
                "provider": "anthropic",
            },
        ],
        "moderator": {"enabled": False},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/simulations", json=payload)
        assert start.status_code == 200
        sim_id = start.json()["simulation_id"]

        # Wait for transcript availability
        for _ in range(50):
            dl = await client.get(f"/api/simulations/{sim_id}/download")
            if dl.status_code == 200:
                data = dl.json()
                assert data["simulation_id"] == sim_id
                assert len(data["messages"]) == 2
                assert data["messages"][0]["name"] == "Agent A"
                assert data["messages"][1]["name"] == "Agent B"
                return
            assert dl.status_code in (409, 200)
            await asyncio.sleep(0.01)

        raise AssertionError("Transcript did not become available in time")


async def test_stop_simulation(app, monkeypatch):
    from app.simulations import turn_executor

    def _fake_build_chat_model(
        *,
        settings,
        model,
        provider=None,
        temperature=None,
        max_tokens=None,
        context_size=None,
    ):  # noqa: ARG001
        # lots of tokens so we have time to stop
        return _FakeStreamingModel(tokens=["x"] * 200)

    monkeypatch.setattr(turn_executor, "build_chat_model", _fake_build_chat_model)

    payload = {
        "topic": "Test stop",
        "mode": "collaboration",
        "stage": "Mode: Collaboration. Build on previous message constructively.",
        "turn_limit": 10,
        "agents": [
            {"name": "Agent A", "model": "gpt-4o-mini", "provider": "openai"},
            {"name": "Agent B", "model": "gpt-4o-mini", "provider": "openai"},
        ],
        "moderator": {"enabled": False},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/simulations", json=payload)
        sim_id = start.json()["simulation_id"]

        stop = await client.post(f"/api/simulations/{sim_id}/stop")
        assert stop.status_code == 200


async def test_collaboration_synthesizer_runs(app, monkeypatch):
    from app.simulations import turn_executor

    def _fake_build_chat_model(
        *,
        settings,
        model,
        provider=None,
        temperature=None,
        max_tokens=None,
        context_size=None,
    ):  # noqa: ARG001
        return _FakeStreamingModel(tokens=[f"[{model}] ok "])

    monkeypatch.setattr(turn_executor, "build_chat_model", _fake_build_chat_model)

    payload = {
        "topic": "Plan a weekend trip",
        "mode": "collaboration",
        "stage": "This is a collaborative setting.",
        "turn_limit": 2,  # 2 rounds with 2 agents = 4 actor turns + 1 synthesizer = 5 total
        "agents": [
            {"name": "Agent A", "model": "gpt-4o-mini", "provider": "openai"},
            {"name": "Agent B", "model": "gpt-4o-mini", "provider": "openai"},
        ],
        "moderator": {"enabled": False},
        "synthesizer": {"enabled": True, "model": "gpt-4o-mini", "frequency_turns": 2},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/simulations", json=payload)
        assert start.status_code == 200
        sim_id = start.json()["simulation_id"]

        for _ in range(80):
            dl = await client.get(f"/api/simulations/{sim_id}/download")
            if dl.status_code == 200:
                data = dl.json()
                # turn_limit=2 with 2 agents = 4 actor turns + 1 synthesizer = 5 total
                assert len(data["messages"]) == 5
                # Check last message is from synthesizer by name
                assert "Synthesizer" in data["messages"][-1]["name"]
                return
            await asyncio.sleep(0.01)

        raise AssertionError("Transcript did not become available in time")


async def test_interaction_mode_runs(app, monkeypatch):
    from app.simulations import turn_executor

    def _fake_build_chat_model(
        *,
        settings,
        model,
        provider=None,
        temperature=None,
        max_tokens=None,
        context_size=None,
    ):  # noqa: ARG001
        return _FakeStreamingModel(tokens=["hi "])

    monkeypatch.setattr(turn_executor, "build_chat_model", _fake_build_chat_model)

    payload = {
        "topic": "Talk about coffee",
        "mode": "interaction",
        "stage": "Mode: Interaction. Converse naturally.",
        "turn_limit": 1,  # 1 round with 2 agents = 2 messages
        "agents": [
            {"name": "Agent A", "model": "gpt-4o-mini", "provider": "openai"},
            {"name": "Agent B", "model": "gpt-4o-mini", "provider": "openai"},
        ],
        "moderator": {"enabled": False},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/simulations", json=payload)
        assert start.status_code == 200
        sim_id = start.json()["simulation_id"]

        for _ in range(50):
            dl = await client.get(f"/api/simulations/{sim_id}/download")
            if dl.status_code == 200:
                data = dl.json()
                assert data["mode"] == "interaction"
                assert len(data["messages"]) == 2
                return
            await asyncio.sleep(0.01)

        raise AssertionError("Transcript did not become available in time")


async def test_stage_is_prepended_to_system_prompt(app, monkeypatch):
    from app.simulations import turn_executor as te

    stage = "STAGE: Speak like a pirate."
    captured: dict[str, str] = {}

    class _CapturingModel:
        async def astream(self, messages):
            # messages[0] is SystemMessage
            captured["system"] = getattr(messages[0], "content", "")
            yield SimpleNamespace(content="ok")

    def _fake_build_chat_model(
        *,
        settings,
        model,
        provider=None,
        temperature=None,
        max_tokens=None,
        context_size=None,
    ):  # noqa: ARG001
        return _CapturingModel()

    monkeypatch.setattr(te, "build_chat_model", _fake_build_chat_model)

    payload = {
        "topic": "Hello",
        "mode": "custom",
        "stage": stage,
        "turn_limit": 1,
        "agents": [
            {
                "name": "Agent A",
                "model": "gpt-4o-mini",
                "system_prompt": "Be concise.",
                "provider": "openai",
            },
            {
                "name": "Agent B",
                "model": "gpt-4o-mini",
                "system_prompt": "Be concise.",
                "provider": "openai",
            },
        ],
        "moderator": {"enabled": False},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/simulations", json=payload)
        assert start.status_code == 200

        sim_id = start.json()["simulation_id"]
        for _ in range(50):
            dl = await client.get(f"/api/simulations/{sim_id}/download")
            if dl.status_code == 200:
                break
            await asyncio.sleep(0.01)

    assert stage in captured["system"]
