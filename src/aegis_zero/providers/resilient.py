"""Retry + model fallback wrapper around any provider."""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from ..core.errors import AegisError, AllProvidersFailed, ProviderError
from ..core.models import Completion, Message
from .base import LLMProvider


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.25

    def delay_for(self, attempt: int, rng: random.Random) -> float:
        raw = min(self.base_delay * (2**attempt), self.max_delay)
        return raw * (1 + rng.uniform(-self.jitter, self.jitter))


class ResilientProvider(LLMProvider):
    """Retries retryable errors with exponential backoff, then falls back
    down an ordered chain of models before giving up."""

    name = "resilient"

    def __init__(
        self,
        inner: LLMProvider,
        *,
        retry: RetryPolicy | None = None,
        fallback_models: Sequence[str] = (),
        primary_attempts: int | None = None,
        sleep: Any = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.inner = inner
        self.retry = retry or RetryPolicy()
        self.fallback_models = tuple(fallback_models)
        # How many times to retry the *primary* model before giving up and
        # walking the fallback chain. Defaults to `retry.attempts` (same as
        # every candidate). Setting it low (e.g. 1) fails fast to a smaller
        # model instead of burning multiple slow attempts on an OOMing 7b.
        self.primary_attempts = primary_attempts
        self._sleep = sleep
        self._rng = rng or random.Random()

    async def complete(
        self, messages: Sequence[Message], *, model: str, **kw: Any
    ) -> Completion:
        import logging

        log = logging.getLogger("aegis.providers.resilient")
        chain = (model, *[m for m in self.fallback_models if m != model])
        failures: list[str] = []
        primary = True

        for candidate in chain:
            attempts = (
                (self.primary_attempts or self.retry.attempts)
                if primary
                else self.retry.attempts
            )
            primary = False
            for attempt in range(attempts):
                try:
                    return await self.inner.complete(messages, model=candidate, **kw)
                except AegisError as exc:
                    failures.append(f"{candidate}: {exc}")
                    if not getattr(exc, "retryable", False):
                        break
                    if attempt == attempts - 1:
                        break
                    await self._sleep(self.retry.delay_for(attempt, self._rng))
            # Inner loop ended without returning -> this candidate failed.
            # Walk to the next candidate, logging the degradation.
            if candidate != chain[-1]:
                log.warning(
                    "model %s failed; falling back to %s",
                    candidate,
                    chain[chain.index(candidate) + 1],
                )

        raise AllProvidersFailed(
            "all models exhausted",
            context={"tried": list(chain), "failures": failures[-4:]},
        )

    async def stream(
        self, messages: Sequence[Message], *, model: str, **kw: Any
    ) -> AsyncIterator[str]:
        """Stream with retry and model fallback.

        Retrying a stream is only safe *before* the first token reaches the
        caller; once output has been yielded a retry would duplicate it. So
        failures are recoverable up to the first token and fatal after it.
        """
        chain = (model, *[m for m in self.fallback_models if m != model])
        failures: list[str] = []

        for candidate in chain:
            for attempt in range(self.retry.attempts):
                emitted = False
                try:
                    async for piece in self.inner.stream(messages, model=candidate, **kw):
                        emitted = True
                        yield piece
                    return
                except AegisError as exc:
                    failures.append(f"{candidate}: {exc}")
                    if emitted:
                        # Partial output is already downstream; retrying
                        # would duplicate it. Fail loudly instead.
                        raise
                    if not getattr(exc, "retryable", False):
                        break
                    if attempt == self.retry.attempts - 1:
                        break
                    await self._sleep(self.retry.delay_for(attempt, self._rng))

        raise AllProvidersFailed(
            "all models exhausted (stream)",
            context={"tried": list(chain), "failures": failures[-4:]},
        )

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        last: Exception | None = None
        for attempt in range(self.retry.attempts):
            try:
                return await self.inner.embed(texts, model=model)
            except AegisError as exc:
                last = exc
                if not getattr(exc, "retryable", False):
                    raise
                await self._sleep(self.retry.delay_for(attempt, self._rng))
        raise ProviderError("embedding failed", context={"cause": str(last)})

    async def aclose(self) -> None:
        await self.inner.aclose()
