from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class InteractionMode(str, Enum):
    debate = "debate"
    collaboration = "collaboration"
    interaction = "interaction"
    custom = "custom"


class AgentConfig(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=128)
    persona: str | None = Field(default=None, max_length=200)
    system_prompt: str | None = None
    debate_side: Literal["for", "against"] | None = None
    responsibility: str | None = None
    provider: Literal["openai", "anthropic", "google", "ollama"]
    # Optional generation settings (omit if None or 0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0)
    context_size: int | None = Field(default=None, ge=0)


class ModeratorConfig(BaseModel):
    enabled: bool = False
    model: str | None = Field(default=None, max_length=128)
    provider: Literal["openai", "anthropic", "google", "ollama"] | None = None
    system_prompt: str | None = None
    frequency_turns: int = Field(default=2, ge=1, le=20)
    # Optional generation settings (omit if None or 0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0)
    context_size: int | None = Field(default=None, ge=0)


class SynthesizerConfig(BaseModel):
    """
    Collaboration-only "lead" that organizes ideas from the actors:
    summarizes progress, merges duplicates, and lists next steps.
    """

    enabled: bool = False
    model: str | None = Field(default=None, max_length=128)
    provider: Literal["openai", "anthropic", "google", "ollama"] | None = None
    system_prompt: str | None = None
    frequency_turns: int = Field(default=2, ge=1, le=20)
    # Optional generation settings (omit if None or 0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=0)
    context_size: int | None = Field(default=None, ge=0)


class StartSimulationRequest(BaseModel):
    topic: str = Field(min_length=1)
    mode: InteractionMode
    stage: str = ""
    turn_limit: int = Field(default=10, ge=1, le=40)

    agents: list[AgentConfig] = Field(min_length=2, max_length=4)
    moderator: ModeratorConfig = Field(default_factory=ModeratorConfig)
    synthesizer: SynthesizerConfig = Field(default_factory=SynthesizerConfig)

    @field_validator("agents")
    @classmethod
    def unique_agent_names(cls, v: list[AgentConfig]) -> list[AgentConfig]:
        names = [a.name.strip().lower() for a in v]
        if len(set(names)) != len(names):
            raise ValueError("Agent names must be unique")
        return v


class SimulationStartedResponse(BaseModel):
    simulation_id: str


class TranscriptMessage(BaseModel):
    role: Literal["agent", "moderator", "synthesizer"]
    name: str
    content: str
    turn: int
    model: str
    agent_id: int


class SimulationTranscript(BaseModel):
    simulation_id: str
    topic: str
    mode: InteractionMode
    messages: list[TranscriptMessage]
