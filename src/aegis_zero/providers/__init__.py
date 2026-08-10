"""LLM provider implementations."""

from __future__ import annotations

from ..core.config import ProviderSettings
from ..core.errors import ConfigError
from .base import LLMProvider
from .echo import EchoProvider, scripted_tool_call
from .openai_compat import OpenAICompatProvider
from .resilient import ResilientProvider, RetryPolicy

__all__ = [
    "EchoProvider",
    "LLMProvider",
    "OpenAICompatProvider",
    "ResilientProvider",
    "RetryPolicy",
    "build_provider",
    "scripted_tool_call",
]


def build_provider(
    settings: ProviderSettings, fallback_models: tuple[str, ...] = ()
) -> LLMProvider:
    """Construct the configured provider wrapped in resilience."""
    kind = settings.kind.lower()
    if kind == "echo":
        inner: LLMProvider = EchoProvider()
    elif kind in ("openai", "openai_compat", "ollama", "vllm", "litellm"):
        inner = OpenAICompatProvider(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
        )
    else:
        raise ConfigError("unknown provider kind", context={"kind": settings.kind})

    return ResilientProvider(
        inner,
        retry=RetryPolicy(attempts=settings.max_retries),
        fallback_models=fallback_models,
    )
