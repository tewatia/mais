from __future__ import annotations

from app.simulations.models import (
    AgentConfig,
    StartSimulationRequest,
    TranscriptMessage,
)
from app.simulations.prompts import agent_system_prompt
from langchain.messages import AIMessage, HumanMessage, SystemMessage


def build_messages_for_turn(
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
    """
    msgs: list = [
        SystemMessage(
            content=agent_system_prompt(
                req=req,
                agent=agent,
                agent_name=agent_name,
                self_agent_id=self_agent_id,
                system_prompt=system_prompt,
                role=role,
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
        other_lines.append(f"{m.name}: {m.content}")

    flush_other()

    # Ensure there's at least one HumanMessage for the model to respond to.
    # Keep it minimal (no explicit "write your next message" instruction).
    if len(msgs) == 1:
        msgs.append(HumanMessage(content="Let's begin."))

    return msgs
