"""Tests for ResilientProvider fallback behaviour (improvement #1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from aegis_zero.core.errors import AllProvidersFailed, ProviderUnavailable
from aegis_zero.core.models import Completion, Message
from aegis_zero.providers.base import LLMProvider
from aegis_zero.providers.resilient import ResilientProvider, RetryPolicy


@dataclass
class _Call:
    model: str


class FlakyProvider(LLMProvider):
    """Fails the first `fail_first` calls for a given model, then succeeds."""

    name = "flaky"

    def __init__(self, fail_first: dict[str, int] | None = None) -> None:
        self.fail_first = dict(fail_first or {})
        self.calls: list[_Call] = []
        self.used_models: list[str] = []

    async def complete(self, messages: Sequence[Message], *, model: str, **kw) -> Completion:
        self.calls.append(_Call(model))
        self.used_models.append(model)
        remaining = self.fail_first.get(model, 0)
        if remaining > 0:
            self.fail_first[model] = remaining - 1
            raise ProviderUnavailable("simulated 500", context={"status": 500})
        return Completion(text=f"ok:{model}", model=model, usage=None, finish_reason="stop")

    async def stream(self, messages, *, model, **kw):
        yield "x"

    async def embed(self, texts, *, model):
        return [[0.0] * 4 for _ in texts]

    async def aclose(self) -> None:
        return None


async def test_fallback_walks_chain_on_primary_failure() -> None:
    inner = FlakyProvider(fail_first={"big": 5})  # big always fails
    rp = ResilientProvider(inner, fallback_models=("small", "tiny"))
    out = await rp.complete([Message(role="user", content="hi")], model="big")
    assert out.text == "ok:small"
    # big failed, then small succeeded.
    assert inner.used_models[0] == "big"
    assert inner.used_models[-1] == "small"


async def test_primary_succeeds_no_fallback() -> None:
    inner = FlakyProvider()
    rp = ResilientProvider(inner, fallback_models=("small",))
    out = await rp.complete([Message(role="user", content="hi")], model="big")
    assert out.text == "ok:big"
    assert inner.used_models == ["big"]


async def test_fail_fast_primary_avoids_repeated_primary_attempts() -> None:
    inner = FlakyProvider(fail_first={"big": 99})  # never recovers
    rp = ResilientProvider(
        inner,
        retry=RetryPolicy(attempts=3),
        fallback_models=("small",),
        primary_attempts=1,  # big should be tried once, then drop to small
    )
    out = await rp.complete([Message(role="user", content="hi")], model="big")
    # big tried exactly once, then small.
    big_tries = [c for c in inner.used_models if c == "big"]
    assert len(big_tries) == 1, f"primary retried too much: {inner.used_models}"
    assert out.text == "ok:small"


async def test_all_models_exhausted_raises() -> None:
    inner = FlakyProvider(fail_first={"big": 99, "small": 99})
    rp = ResilientProvider(inner, fallback_models=("small",), primary_attempts=1)
    with pytest.raises(AllProvidersFailed):
        await rp.complete([Message(role="user", content="hi")], model="big")
