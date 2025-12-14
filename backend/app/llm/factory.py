from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

Provider = Literal["openai", "anthropic", "google"]


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str


def infer_provider(model: str) -> Provider:
    m = model.lower()
    if m.startswith("gpt-") or "openai" in m:
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "google"
    raise FriendlyLLMError(
        "Unknown model/provider. Choose a supported model (gpt-*, claude-*, gemini-*)."
    )


def build_chat_model(
    *, settings: Settings, model: str, provider: Provider | None = None
):
    prov = provider or infer_provider(model)

    if prov == "openai":
        if not settings.openai_api_key:
            raise FriendlyLLMError("OpenAI API key is not configured on the server.")
        return ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=0.7)

    if prov == "anthropic":
        if not settings.anthropic_api_key:
            raise FriendlyLLMError("Anthropic API key is not configured on the server.")
        return ChatAnthropic(
            model=model, api_key=settings.anthropic_api_key, temperature=0.7
        )

    if prov == "google":
        if not settings.google_api_key:
            raise FriendlyLLMError("Google API key is not configured on the server.")
        return ChatGoogleGenerativeAI(
            model=model, google_api_key=settings.google_api_key, temperature=0.7
        )

    raise FriendlyLLMError("Unsupported provider.")
