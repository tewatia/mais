from __future__ import annotations

import json
import re

from app.simulations.models import (
    AgentConfig,
    InteractionMode,
    StartSimulationRequest,
)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}")


def parse_termination_payload(text: str) -> tuple[bool, str]:
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


def append_json_contract(*, base_prompt: str, kind: str, final_call: bool) -> str:
    """
    Keep JSON termination as a backend implementation detail by appending this contract
    regardless of what the UI prompt contains.
    """
    base = (base_prompt or "").strip()

    contract = (
        "Output MUST be valid JSON:\n"
        '{"terminate": false, "message": "<your text>"}\n\n'
        + (
            "The discussion is now complete. You must provide the synthesis/summary now.\n"
            "Set terminate=true.\n"
            if final_call
            else "If you have enough information to conclude early, set terminate=true and provide the concluding summary.\n"
        )
    ).strip()

    if base:
        return (base + "\n\n" + contract).strip()
    return contract


def agent_system_prompt(
    *,
    req: StartSimulationRequest,
    agent: AgentConfig | None,
    agent_name: str,
    self_agent_id: int,
    system_prompt: str | None,
    role: str,
) -> str:
    stage_text = (req.stage or "").strip()
    base = (system_prompt or "").strip()
    names = [a.name for a in req.agents]
    others = [
        agent.name for i, agent in enumerate(req.agents, start=1) if i != self_agent_id
    ]
    parts: list[str] = []
    if stage_text:
        parts.append("Setting:\n" + stage_text)

    if role == "agent":
        parts.append(f"You are {agent_name}.")
        if base:
            parts.append(base)
        if len(others) == 1:
            parts.append(f"You are speaking with {others[0]}.")
        elif others:
            parts.append("You are speaking with: " + ", ".join(others) + ".")

        if req.moderator and req.moderator.enabled:
            parts.append("Moderator Morris is present to moderate the discussion.")
        if req.synthesizer and req.synthesizer.enabled:
            parts.append("Synthesizer Sophie is present to synthesize the results.")

    else:
        parts.append("Participants are: " + ", ".join(names) + ".")

    parts.append(f"Topic:\n{req.topic}")
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
    if role != "agent":
        parts.append(f"You are {agent_name}.")
        if base:
            parts.append(base)
    return "\n\n".join(parts)
