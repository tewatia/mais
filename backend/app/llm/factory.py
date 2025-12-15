from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama

Provider = Literal["openai", "anthropic", "google", "ollama"]


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str


def build_chat_model(*, settings: Settings, model: str, provider: Provider):
    if provider == "openai":
        if not settings.openai_api_key:
            raise FriendlyLLMError("OpenAI API key is not configured on the server.")
        return ChatOpenAI(model=model, api_key=settings.openai_api_key, temperature=0.7)

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise FriendlyLLMError("Anthropic API key is not configured on the server.")
        return ChatAnthropic(
            model=model, api_key=settings.anthropic_api_key, temperature=0.7
        )

    if provider == "google":
        if not settings.google_api_key:
            raise FriendlyLLMError("Google API key is not configured on the server.")
        return ChatGoogleGenerativeAI(
            model=model, google_api_key=settings.google_api_key, temperature=0.7
        )

    if provider == "ollama":
        # Ollama typically runs locally without an API key, but we check if the URL is set if needed.
        # For now, we assume default local URL or that it's handled by environment variables.
        # ChatOllama connects to http://localhost:11434 by default.
        return ChatOllama(model=model, temperature=0.7)

    raise FriendlyLLMError(f"Unsupported provider: {provider}")
