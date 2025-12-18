from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings
from app.llm.errors import FriendlyLLMError
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

Provider = Literal["openai", "anthropic", "google", "ollama"]


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model: str


def build_chat_model(
    *,
    settings: Settings,
    model: str,
    provider: Provider,
    temperature: float | None = None,
    max_tokens: int | None = None,
    context_size: int | None = None,
):
    """
    Build a LangChain chat model with optional generation settings.

    - temperature: 0.0..2.0 (defaults provider-default)
    - max_tokens: max output tokens (omitted if None or 0)
    - context_size: context window (omitted if None or 0; provider-specific param name)
    """
    if provider == "openai":
        if not settings.openai_api_key:
            raise FriendlyLLMError("OpenAI API key is not configured on the server.")
        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": settings.openai_api_key,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        # OpenAI doesn't expose a context window override; it's inferred from model ID.
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise FriendlyLLMError("Anthropic API key is not configured on the server.")
        kwargs = {
            "model_name": model,
            "api_key": settings.anthropic_api_key,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens:
            kwargs["max_tokens_to_sample"] = max_tokens
        # Anthropic doesn't expose a context window override.
        return ChatAnthropic(**kwargs)

    if provider == "google":
        if not settings.google_api_key:
            raise FriendlyLLMError("Google API key is not configured on the server.")
        kwargs = {
            "model": model,
            "google_api_key": settings.google_api_key,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        # Google doesn't expose a context window override.
        return ChatGoogleGenerativeAI(**kwargs)

    if provider == "ollama":
        # Ollama typically runs locally without an API key.
        # ChatOllama connects to http://localhost:11434 by default.
        kwargs = {"model": model}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens:
            kwargs["num_predict"] = max_tokens
        if context_size:
            kwargs["num_ctx"] = context_size
        return ChatOllama(**kwargs)

    raise FriendlyLLMError(f"Unsupported provider: {provider}")
