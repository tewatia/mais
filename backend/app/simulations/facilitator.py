from __future__ import annotations

import logging
from typing import Literal

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from app.simulations.events import SimulationEvent
from app.simulations.models import (
    ModeratorConfig,
    StartSimulationRequest,
    SynthesizerConfig,
    TranscriptMessage,
)
from app.simulations.prompts import append_json_contract
from app.simulations.state import SimulationState
from app.simulations.turn_executor import stream_one_turn

logger = logging.getLogger(__name__)


async def run_facilitator(
    *,
    state: SimulationState,
    settings: Settings,
    req: StartSimulationRequest,
    role: Literal["moderator", "synthesizer"],
    config: ModeratorConfig | SynthesizerConfig,
    name: str,
    turn: int,
    transcript: list[TranscriptMessage],
    final_call: bool,
) -> tuple[bool, int]:
    """
    Run a facilitator (moderator or synthesizer) turn.
    Returns (terminate, new_turn).
    """
    agent_id = -1 if role == "moderator" else -2
    default_prompt = (
        "Summarize the debate neutrally and suggest the next focus/questions."
        if role == "moderator"
        else "Summarize progress, merge duplicates, and list next steps using only what participants already said."
    )

    turn += 1
    try:
        terminate = await stream_one_turn(
            state=state,
            settings=settings,
            req=req,
            role=role,
            name=name,
            model=config.model,
            provider=config.provider,
            system_prompt=append_json_contract(
                base_prompt=(config.system_prompt or default_prompt),
                kind=role,
                final_call=final_call,
            ),
            transcript=transcript,
            turn=turn,
            agent_id=agent_id,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            context_size=config.context_size,
        )
        return terminate, turn
    except FriendlyLLMError as e:
        logger.warning(
            f"friendly error during {role} turn",
            extra={
                "simulation_id": state.simulation_id,
                "role": role,
                "error": str(e),
            },
        )
        await state.publish(SimulationEvent(type="error", data={"message": str(e)}))
        await state.publish(SimulationEvent(type="status", data={"status": "error"}))
        raise
    except Exception:
        logger.exception(
            f"{role} turn failed",
            extra={"simulation_id": state.simulation_id, "role": role},
        )
        await state.publish(
            SimulationEvent(
                type="error",
                data={"message": f"{role.capitalize()} model call failed."},
            )
        )
        await state.publish(SimulationEvent(type="status", data={"status": "error"}))
        raise
