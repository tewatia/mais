from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from app.llm.factory import build_chat_model
from app.simulations.events import SimulationEvent
from app.simulations.models import (
    AgentConfig,
    InteractionMode,
    SimulationTranscript,
    StartSimulationRequest,
    TranscriptMessage,
)
from app.simulations.state import SimulationState
from langchain.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def _parse_termination_payload(text: str) -> tuple[bool, str]:
    """
    Parse a moderator/synthesizer response of the form:
      {"terminate": true/false, "message": "..."}

    Accepts optional code fences and extra whitespace. Falls back to:
      terminate=false, message=<original text>
    """
    raw = (text or "").strip()
    if not raw:
        return False, ""

    # Strip common code fences
    if raw.startswith("```"):
        raw = raw.strip("`").strip()

    m = _JSON_BLOCK_RE.search(raw)
    if not m:
        return False, (text or "").strip()

    try:
        obj = json.loads(m.group(0))
    except Exception:
        return False, (text or "").strip()

    terminate = bool(obj.get("terminate", False))
    message = obj.get("message", None)
    if not isinstance(message, str):
        message = (text or "").strip()
    return terminate, message.strip()


def _append_json_contract(*, base_prompt: str, kind: str, final_call: bool) -> str:
    """
    Keep JSON termination as a backend implementation detail by appending this contract
    regardless of what the UI prompt contains.
    """
    base = (base_prompt or "").strip()
    if kind == "synthesizer":
        heading = "You are the collaboration lead."
        bullet = (
            "- Summarize progress so far (brief)\n"
            "- Merge duplicates / reconcile overlaps\n"
            "- List concrete next steps"
        )
    else:
        heading = "You are a debate moderator."
        bullet = (
            "- Briefly summarize the debate so far (neutral)\n"
            "- Merge duplicates / reconcile overlaps\n"
            "- Suggest next focus / questions to resolve"
        )

    contract = (
        f"{heading}\n"
        "Do NOT introduce new ideas.\n\n"
        "Output MUST be valid JSON:\n"
        '{"terminate": false, "message": "<your text>"}\n\n'
        "In your message:\n"
        f"{bullet}\n\n"
        + (
            "The discussion is now complete. Provide the closing synthesis/summary now.\n"
            "Set terminate=true.\n"
            if final_call
            else "If you have enough information to conclude early, set terminate=true and provide the concluding summary.\n"
        )
    ).strip()

    if base:
        return (base + "\n\n" + contract).strip()
    return contract


def _agent_system_prompt(
    *,
    req: StartSimulationRequest,
    agent: AgentConfig | None,
    agent_name: str,
    self_agent_id: int,
    system_prompt: str | None,
) -> str:
    stage_text = req.stage.strip()
    base = (system_prompt or "").strip()
    names = [a.name for a in req.agents]
    others = [n for n in names if n != agent_name]
    parts: list[str] = []
    parts.append(f"Topic:\n{req.topic}")
    parts.append(f"You are {agent_name}.")
    if len(others) == 1:
        parts.append(f"You are speaking with {others[0]}.")
    elif others:
        parts.append("You are speaking with: " + ", ".join(others) + ".")

    # Mode-specific guidance
    if req.mode == InteractionMode.debate and agent:
        # Deterministic auto-side when not specified: alternate by actor index (agent_id is 1-based).
        side_value = agent.debate_side or (
            "for" if (self_agent_id % 2 == 1) else "against"
        )
        side = "FOR" if side_value == "for" else "AGAINST"
        parts.append(f"Your position: argue {side} the topic.")
    if req.mode == InteractionMode.collaboration and agent and agent.responsibility:
        parts.append(f"Your responsibility: {agent.responsibility.strip()}")

    if base:
        parts.append(base)
    if stage_text:
        parts.append("Setting:\n" + stage_text)
    return "\n\n".join(parts)


def _build_messages_for_turn(
    *,
    req: StartSimulationRequest,
    agent: AgentConfig | None,
    agent_name: str,
    role: str,
    self_agent_id: int,
    system_prompt: str | None,
    transcript: list[TranscriptMessage],
) -> list:
    """
    Build an explicit message array rather than stuffing everything into one HumanMessage.

    - The current agent's prior messages are represented as AIMessage.
    - Other actors' messages are represented as HumanMessage.
      - To keep a strict AI/Human alternating structure, we group other-speaker messages
        into a single HumanMessage when needed.
      - If there are >2 actors, we prefix with "<name>: ..." for clarity.
    """
    msgs: list = [
        SystemMessage(
            content=_agent_system_prompt(
                req=req,
                agent=agent,
                agent_name=agent_name,
                self_agent_id=self_agent_id,
                system_prompt=system_prompt,
            )
        )
    ]
    n_agents = len(req.agents)

    other_lines: list[str] = []

    def flush_other() -> None:
        nonlocal other_lines
        if not other_lines:
            return
        msgs.append(HumanMessage(content="\n".join(other_lines).strip()))
        other_lines = []

    def is_self_message(m: TranscriptMessage) -> bool:
        return m.role == role and m.agent_id == self_agent_id

    for m in transcript:
        if is_self_message(m):
            flush_other()
            msgs.append(AIMessage(content=m.content))
            continue

        # Anything else is treated as "other" and accumulated into the next HumanMessage.
        if m.role == "agent":
            # With 2 actors, omit prefixes for agents (but keep prefixes for moderator/synthesizer).
            if n_agents <= 2 and role == "agent":
                other_lines.append(m.content)
            else:
                other_lines.append(f"{m.name}: {m.content}")
        else:
            other_lines.append(f"{m.name}: {m.content}")

    flush_other()

    # Ensure there's at least one HumanMessage for the model to respond to.
    # Keep it minimal (no explicit "write your next message" instruction).
    if len(msgs) == 1:
        msgs.append(HumanMessage(content="Let's begin."))

    return msgs


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
    llm = build_chat_model(
        settings=settings, model=model, provider=provider
    )  # may raise FriendlyLLMError
    req = state.request
    _ = topic  # topic is available in req.topic; kept for backward-compatible signature
    agent_cfg = (
        next((a for a in req.agents if a.name == name), None)
        if role == "agent"
        else None
    )
    messages = _build_messages_for_turn(
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

    # print("messages:")
    # print(role, name, model, provider, system_prompt, topic, transcript, turn)
    # print(messages)
    # print("--------------------------------")
    # print("--------------------------------")
    # print("--------------------------------")
    content_parts: list[str] = []
    async for chunk in llm.astream(messages):
        if state.cancel_event.is_set():
            return
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

    full = "".join(content_parts).strip()
    terminate = False
    final_content = full
    if role in {"moderator", "synthesizer"}:
        terminate, final_content = _parse_termination_payload(full)
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
    return terminate


async def run_simulation(*, state: SimulationState, settings: Settings) -> None:
    req = state.request

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
                        name="Synthesizer",
                        model=req.synthesizer.model,
                        provider=req.synthesizer.provider,
                        system_prompt=_append_json_contract(
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
                        name="Moderator",
                        model=req.moderator.model,
                        provider=req.moderator.provider,
                        system_prompt=_append_json_contract(
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
                    system_prompt=_append_json_contract(
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
            await state.publish(
                SimulationEvent(type="status", data={"status": "stopped"})
            )
        else:
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
