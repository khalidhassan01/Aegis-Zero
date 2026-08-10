"""Provider abstraction: any chat model behind one async interface."""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.models import Completion, Message


class LLMProvider(abc.ABC):
    """An async chat-completion backend."""

    name: str = "provider"

    @abc.abstractmethod
    async def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Completion:
        """Return a single completion."""

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Defaults to a single chunk from ``complete``."""
        result = await self.complete(
            messages, model=model, temperature=temperature, max_tokens=max_tokens
        )
        yield result.text

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        raise NotImplementedError(f"{self.name} does not support embeddings")

    async def aclose(self) -> None:
        return None
