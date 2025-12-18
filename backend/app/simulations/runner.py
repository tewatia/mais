from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from app.simulations.events import SimulationEvent
from app.simulations.facilitator import run_facilitator
from app.simulations.models import (
    InteractionMode,
    SimulationTranscript,
    TranscriptMessage,
)
from app.simulations.state import SimulationState
from app.simulations.turn_executor import stream_one_turn

logger = logging.getLogger(__name__)


async def run_simulation(*, state: SimulationState, settings: Settings) -> None:
    """
    Main simulation loop that orchestrates agent, moderator, and synthesizer turns.
    """
    req = state.request
    logger.info(
        "starting simulation",
        extra={
            "simulation_id": state.simulation_id,
            "env": settings.env,
            "mode": req.mode,
            "agents": len(req.agents),
        },
    )

    # Validate limits
    if req.turn_limit > settings.max_turn_limit:
        raise FriendlyLLMError("Turn limit exceeds server maximum.")
    if len(req.agents) > settings.max_agents:
        raise FriendlyLLMError("Too many agents for this server.")

    # Wait for subscribers (orphan detection)
    if settings.env != "test" and settings.orphan_grace_seconds > 0:
        start_wait = time.monotonic()
        while not state.cancel_event.is_set() and not state.subscribers:
            if time.monotonic() - start_wait >= settings.orphan_grace_seconds:
                logger.info(
                    "stopping orphaned simulation (no subscribers)",
                    extra={"simulation_id": state.simulation_id},
                )
                state.cancel_event.set()
                return
            await asyncio.sleep(0.05)

    await state.publish(SimulationEvent(type="status", data={"status": "started"}))

    transcript: list[TranscriptMessage] = []
    # turn_limit is interpreted as "number of rounds" (each agent speaks once per round)
    max_actor_turns = req.turn_limit * len(req.agents)
    actor_turns = 0
    turn = 0  # Sequential message index for streaming/transcript

    try:
        terminated_early = False

        while actor_turns < max_actor_turns and not state.cancel_event.is_set():
            # Check for subscriber disconnection
            if (
                settings.env != "test"
                and settings.orphan_grace_seconds > 0
                and not state.subscribers
                and time.monotonic() - state.last_subscriber_change
                >= settings.orphan_grace_seconds
            ):
                logger.info(
                    "subscribers disconnected, stopping",
                    extra={"simulation_id": state.simulation_id},
                )
                state.cancel_event.set()
                break

            # === Agent turns ===
            executed_agents = 0
            for agent_id, agent in enumerate(req.agents, start=1):
                if actor_turns >= max_actor_turns or state.cancel_event.is_set():
                    break
                actor_turns += 1
                turn += 1
                executed_agents += 1

                try:
                    await stream_one_turn(
                        state=state,
                        settings=settings,
                        req=req,
                        role="agent",
                        name=agent.name,
                        model=agent.model,
                        provider=agent.provider,
                        system_prompt=agent.system_prompt,
                        transcript=transcript,
                        turn=turn,
                        agent_id=agent_id,
                        temperature=agent.temperature,
                        max_tokens=agent.max_tokens,
                        context_size=agent.context_size,
                    )
                except FriendlyLLMError as e:
                    logger.warning(
                        "friendly error during agent turn",
                        extra={
                            "simulation_id": state.simulation_id,
                            "agent": agent.name,
                            "error": str(e),
                        },
                    )
                    await state.publish(
                        SimulationEvent(type="error", data={"message": str(e)})
                    )
                    await state.publish(
                        SimulationEvent(type="status", data={"status": "error"})
                    )
                    return
                except Exception:
                    logger.exception(
                        "agent turn failed",
                        extra={
                            "simulation_id": state.simulation_id,
                            "agent": agent.name,
                        },
                    )
                    await state.publish(
                        SimulationEvent(
                            type="error",
                            data={
                                "message": "A model call failed. Check configuration and try again."
                            },
                        )
                    )
                    await state.publish(
                        SimulationEvent(type="status", data={"status": "error"})
                    )
                    return

            # === Synthesizer turn (collaboration mode) ===
            # Runs after N collaboration rounds OR at the end
            final_call = actor_turns >= max_actor_turns
            if (
                req.synthesizer.enabled
                and req.mode == InteractionMode.collaboration
                and not state.cancel_event.is_set()
                and req.synthesizer.model
                and actor_turns > 0
                and (
                    actor_turns % (2 * req.synthesizer.frequency_turns) == 0
                    or final_call
                )
            ):
                try:
                    terminate, turn = await run_facilitator(
                        state=state,
                        settings=settings,
                        req=req,
                        role="synthesizer",
                        config=req.synthesizer,
                        name="Synthesizer Sophie",
                        turn=turn,
                        transcript=transcript,
                        final_call=final_call,
                    )
                    if terminate:
                        terminated_early = True

                except Exception:
                    return

            # === Moderator turn (debate mode) ===
            # Runs every N actor turns OR at the end
            if (
                req.moderator.enabled
                and req.mode == InteractionMode.debate
                and not state.cancel_event.is_set()
                and req.moderator.model
                and actor_turns > 0
                and (
                    actor_turns % (2 * req.moderator.frequency_turns) == 0 or final_call
                )
            ):
                try:
                    terminate, turn = await run_facilitator(
                        state=state,
                        settings=settings,
                        req=req,
                        role="moderator",
                        config=req.moderator,
                        name="Moderator Morris",
                        turn=turn,
                        transcript=transcript,
                        final_call=final_call,
                    )
                    if terminate:
                        terminated_early = True

                except Exception:
                    return

            if terminated_early:
                break

        # Publish final status
        if state.cancel_event.is_set():
            logger.info(
                "simulation stopped", extra={"simulation_id": state.simulation_id}
            )
            await state.publish(
                SimulationEvent(type="status", data={"status": "stopped"})
            )
        else:
            logger.info(
                "simulation finished", extra={"simulation_id": state.simulation_id}
            )
            await state.publish(
                SimulationEvent(type="status", data={"status": "finished"})
            )
    finally:
        state.transcript = SimulationTranscript(
            simulation_id=state.simulation_id,
            topic=req.topic,
            mode=req.mode,
            messages=transcript,
        )
