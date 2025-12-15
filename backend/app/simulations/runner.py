from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from app.llm.factory import build_chat_model
from app.simulations.events import SimulationEvent
from app.simulations.messages import build_messages_for_turn
from app.simulations.models import (
    InteractionMode,
    SimulationTranscript,
    TranscriptMessage,
)
from app.simulations.prompts import append_json_contract, parse_termination_payload
from app.simulations.state import SimulationState

logger = logging.getLogger(__name__)


async def _stream_one_turn(
    *,
    state: SimulationState,
    settings: Settings,
    role: str,
    name: str,
    model: str,
    provider: str | None,
    system_prompt: str | None,
    topic: str,
    transcript: list[TranscriptMessage],
    agent_id: int,
    turn: int,
) -> bool:
    logger.debug(
        "starting turn",
        extra={
            "simulation_id": state.simulation_id,
            "turn": turn,
            "role": role,
            "name": name,
            "model": model,
            "provider": provider,
        },
    )

    try:
        llm = build_chat_model(
            settings=settings, model=model, provider=provider
        )  # may raise FriendlyLLMError
    except FriendlyLLMError as e:
        logger.warning(
            "failed to build chat model",
            extra={
                "simulation_id": state.simulation_id,
                "model": model,
                "provider": provider,
                "error": str(e),
            },
        )
        raise

    req = state.request
    _ = topic  # topic is available in req.topic; kept for backward-compatible signature
    agent_cfg = req.agents[agent_id - 1] if role == "agent" and agent_id > 0 else None
    messages = build_messages_for_turn(
        req=req,
        agent=agent_cfg,
        agent_name=name,
        role=role,
        self_agent_id=agent_id,
        system_prompt=system_prompt,
        transcript=transcript,
    )

    await state.publish(
        SimulationEvent(
            type="status", data={"status": "typing", "name": name, "turn": turn}
        )
    )

    content_parts: list[str] = []

    try:
        async for chunk in llm.astream(messages):
            if state.cancel_event.is_set():
                logger.info(
                    "turn cancelled mid-stream",
                    extra={"simulation_id": state.simulation_id, "turn": turn},
                )
                return False
            token = getattr(chunk, "content", None) or ""
            if token:
                content_parts.append(token)
                await state.publish(
                    SimulationEvent(
                        type="token",
                        data={
                            "name": name,
                            "turn": turn,
                            "token": token,
                            "role": role,
                            "agent_id": agent_id,
                        },
                    )
                )
    except Exception as e:
        logger.error(
            "error streaming tokens",
            exc_info=True,
            extra={
                "simulation_id": state.simulation_id,
                "turn": turn,
                "name": name,
            },
        )
        raise

    full = "".join(content_parts).strip()
    terminate = False
    final_content = full
    if role in {"moderator", "synthesizer"}:
        terminate, final_content = parse_termination_payload(full)

    transcript.append(
        TranscriptMessage(
            role=role,
            name=name,
            content=final_content,
            turn=turn,
            model=model,
            agent_id=agent_id,
        )
    )
    await state.publish(
        SimulationEvent(
            type="message",
            data={
                "name": name,
                "turn": turn,
                "content": final_content,
                "role": role,
                "model": model,
                "agent_id": agent_id,
            },
        )
    )
    logger.debug(
        "turn completed",
        extra={
            "simulation_id": state.simulation_id,
            "turn": turn,
            "name": name,
            "terminate": terminate,
            "content_len": len(final_content),
        },
    )
    return terminate


async def run_simulation(*, state: SimulationState, settings: Settings) -> None:
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

    if req.turn_limit > settings.max_turn_limit:
        raise FriendlyLLMError("Turn limit exceeds server maximum.")
    if len(req.agents) > settings.max_agents:
        raise FriendlyLLMError("Too many agents for this server.")
    if len(req.topic) > settings.max_topic_chars:
        raise FriendlyLLMError("Topic is too long.")
    if len(req.stage) > settings.max_stage_chars:
        raise FriendlyLLMError("Stage text is too long.")
    if (
        req.moderator.system_prompt
        and len(req.moderator.system_prompt) > settings.max_prompt_chars
    ):
        raise FriendlyLLMError("System prompt too long for moderator.")
    if (
        req.synthesizer.system_prompt
        and len(req.synthesizer.system_prompt) > settings.max_prompt_chars
    ):
        raise FriendlyLLMError("System prompt too long for synthesizer.")

    # If nobody connects to the event stream, auto-stop after a grace period.
    # Disabled in env=test to keep unit tests fast/deterministic without SSE wiring.
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
    # `turn_limit` is treated as a limit on actor turns (not counting moderator/synthesizer).
    actor_turns = 0
    # `turn` is the sequential message index used for streaming/transcript metadata.
    turn = 0
    try:
        terminated_early = False
        collaboration_rounds = 0
        synth_concluded = False

        while actor_turns < req.turn_limit and not state.cancel_event.is_set():
            # If all listeners disconnected, stop after grace period.
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
            executed_agents = 0
            for agent_id, agent in enumerate(req.agents, start=1):
                if actor_turns >= req.turn_limit or state.cancel_event.is_set():
                    break
                actor_turns += 1
                turn += 1
                executed_agents += 1

                if (
                    agent.system_prompt
                    and len(agent.system_prompt) > settings.max_prompt_chars
                ):
                    raise FriendlyLLMError(
                        f"System prompt too long for agent '{agent.name}'."
                    )

                try:
                    await _stream_one_turn(
                        state=state,
                        settings=settings,
                        role="agent",
                        name=agent.name,
                        model=agent.model,
                        provider=agent.provider,
                        system_prompt=agent.system_prompt,
                        topic=req.topic,
                        transcript=transcript,
                        turn=turn,
                        agent_id=agent_id,
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

            if executed_agents == len(req.agents) and executed_agents > 0:
                collaboration_rounds += 1

            # Synthesizer/Lead: runs after N collaboration rounds (full passes over actors),
            # and ALWAYS runs once at the end if enabled.
            if (
                req.synthesizer.enabled
                and req.mode == InteractionMode.collaboration
                and not state.cancel_event.is_set()
                and req.synthesizer.model
                and collaboration_rounds > 0
                and (collaboration_rounds % req.synthesizer.frequency_turns == 0)
            ):
                # Not final if there are still actor turns remaining.
                final_call = actor_turns >= req.turn_limit
                turn += 1
                try:
                    terminate = await _stream_one_turn(
                        state=state,
                        settings=settings,
                        role="synthesizer",
                        name="Synthesizer Sophie",
                        model=req.synthesizer.model,
                        provider=req.synthesizer.provider,
                        system_prompt=append_json_contract(
                            base_prompt=(
                                req.synthesizer.system_prompt
                                or "Summarize progress, merge duplicates, and list next steps using only what participants already said."
                            ),
                            kind="synthesizer",
                            final_call=final_call,
                        ),
                        topic=req.topic,
                        transcript=transcript,
                        turn=turn,
                        agent_id=-2,
                    )
                    if terminate:
                        terminated_early = True
                        synth_concluded = True
                except FriendlyLLMError as e:
                    logger.warning(
                        "friendly error during synthesizer turn",
                        extra={
                            "simulation_id": state.simulation_id,
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
                        "synthesizer turn failed",
                        extra={"simulation_id": state.simulation_id},
                    )
                    await state.publish(
                        SimulationEvent(
                            type="error",
                            data={"message": "Synthesizer model call failed."},
                        )
                    )
                    await state.publish(
                        SimulationEvent(type="status", data={"status": "error"})
                    )
                    return

            # Moderator (MVP): only when enabled and in debate mode
            if (
                req.moderator.enabled
                and req.mode == InteractionMode.debate
                and not state.cancel_event.is_set()
                and req.moderator.model
                and turn % req.moderator.frequency_turns == 0
            ):
                # Note: turn_limit is actor turns; moderator does not count against it.
                final_call = actor_turns >= req.turn_limit
                turn += 1
                try:
                    terminate = await _stream_one_turn(
                        state=state,
                        settings=settings,
                        role="moderator",
                        name="Moderator Morris",
                        model=req.moderator.model,
                        provider=req.moderator.provider,
                        system_prompt=append_json_contract(
                            base_prompt=(
                                req.moderator.system_prompt
                                or "Summarize the debate neutrally and suggest the next focus/questions."
                            ),
                            kind="moderator",
                            final_call=final_call,
                        ),
                        topic=req.topic,
                        transcript=transcript,
                        turn=turn,
                        agent_id=-1,
                    )
                    if terminate:
                        terminated_early = True
                except FriendlyLLMError as e:
                    logger.warning(
                        "friendly error during moderator turn",
                        extra={
                            "simulation_id": state.simulation_id,
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
                        "moderator turn failed",
                        extra={"simulation_id": state.simulation_id},
                    )
                    await state.publish(
                        SimulationEvent(
                            type="error",
                            data={"message": "Moderator model call failed."},
                        )
                    )
                    await state.publish(
                        SimulationEvent(type="status", data={"status": "error"})
                    )
                    return

            if terminated_early:
                break

        # Force a final synthesizer conclusion if enabled in collaboration mode,
        # even if it wasn't scheduled at that moment.
        if (
            not state.cancel_event.is_set()
            and not terminated_early
            and req.synthesizer.enabled
            and req.mode == InteractionMode.collaboration
            and req.synthesizer.model
            and not synth_concluded
        ):
            turn += 1
            try:
                await _stream_one_turn(
                    state=state,
                    settings=settings,
                    role="synthesizer",
                    name="Synthesizer",
                    model=req.synthesizer.model,
                    provider=req.synthesizer.provider,
                    system_prompt=append_json_contract(
                        base_prompt=(
                            req.synthesizer.system_prompt
                            or "Summarize progress, merge duplicates, and list next steps using only what participants already said."
                        ),
                        kind="synthesizer",
                        final_call=True,
                    ),
                    topic=req.topic,
                    transcript=transcript,
                    turn=turn,
                    agent_id=-2,
                )
            except FriendlyLLMError as e:
                logger.warning(
                    "friendly error during final synthesizer turn",
                    extra={
                        "simulation_id": state.simulation_id,
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
                    "synthesizer final turn failed",
                    extra={"simulation_id": state.simulation_id},
                )
                await state.publish(
                    SimulationEvent(
                        type="error", data={"message": "Synthesizer model call failed."}
                    )
                )
                await state.publish(
                    SimulationEvent(type="status", data={"status": "error"})
                )
                return

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
