from __future__ import annotations

import logging
import re

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from app.llm.factory import build_chat_model
from app.simulations.events import SimulationEvent
from app.simulations.messages import build_messages_for_turn
from app.simulations.models import StartSimulationRequest, TranscriptMessage
from app.simulations.prompts import parse_termination_payload
from app.simulations.state import SimulationState

logger = logging.getLogger(__name__)


def strip_user_name_from_final_content(final_content: str, name: str) -> str:
    """
    Strip the agent/moderator/synthesizer name from the beginning of the content.
    Handles names with spaces, numbers, and special characters.
    """
    # Escape the name to handle special regex characters
    escaped_name = re.escape(name)
    # Try to match "Name: " at the start (with optional whitespace)
    pattern = rf"^{escaped_name}\s*:\s*"
    return re.sub(pattern, "", final_content, count=1)


async def stream_one_turn(
    *,
    state: SimulationState,
    settings: Settings,
    req: StartSimulationRequest,
    role: str,
    name: str,
    model: str,
    provider: str | None,
    system_prompt: str | None,
    transcript: list[TranscriptMessage],
    agent_id: int,
    turn: int,
    temperature: float | None = None,
    max_tokens: int | None = None,
    context_size: int | None = None,
) -> bool:
    """
    Stream a single turn for an agent, moderator, or synthesizer.
    Returns True if termination was requested, False otherwise.
    """
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
            settings=settings,
            model=model,
            provider=provider,
            temperature=temperature,
            max_tokens=max_tokens,
            context_size=context_size,
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

    # Strip the speaker's name if the model included it at the beginning
    final_content = strip_user_name_from_final_content(final_content, name)

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
