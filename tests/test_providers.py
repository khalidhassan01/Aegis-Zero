from __future__ import annotations

import pytest

from aegis_zero.core.errors import (
    AllProvidersFailed,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
)
from aegis_zero.core.models import Completion, Message, Usage
from aegis_zero.providers import EchoProvider, ResilientProvider, RetryPolicy
from aegis_zero.providers.base import LLMProvider
from aegis_zero.providers.openai_compat import _parse_tool_calls

MSGS = [Message(role="user", content="hi")]


class Flaky(LLMProvider):
    """Fails a set number of times, then succeeds."""

    def __init__(self, fails: int, exc=ProviderTimeout):
        self.fails = fails
        self.exc = exc
        self.attempts = 0
        self.models_seen: list[str] = []

    async def complete(self, messages, *, model, **kw):
        self.attempts += 1
        self.models_seen.append(model)
        if self.attempts <= self.fails:
            raise self.exc("boom")
        return Completion(text="ok", model=model, usage=Usage(1, 1))


async def test_echo_returns_scripted_then_echoes():
    p = EchoProvider(script=["first"])
    assert (await p.complete(MSGS, model="m")).text == "first"
    assert (await p.complete(MSGS, model="m")).text == "echo: hi"


async def test_echo_embeddings_are_deterministic_and_normalised():
    p = EchoProvider(vector_size=32)
    a, b = await p.embed(["x", "x"], model="e")
    assert a == b and len(a) == 32
    assert abs(sum(v * v for v in a) ** 0.5 - 1.0) < 1e-9


async def test_retry_recovers_from_transient_failures():
    inner = Flaky(fails=2)
    r = ResilientProvider(inner, retry=RetryPolicy(attempts=3),
                          sleep=_nosleep)
    assert (await r.complete(MSGS, model="m")).text == "ok"
    assert inner.attempts == 3


async def test_non_retryable_error_does_not_retry_same_model():
    inner = Flaky(fails=99, exc=ProviderError)
    r = ResilientProvider(inner, retry=RetryPolicy(attempts=5), sleep=_nosleep)
    with pytest.raises(AllProvidersFailed):
        await r.complete(MSGS, model="m")
    assert inner.attempts == 1


async def test_falls_back_to_next_model():
    class OnlyBackup(LLMProvider):
        async def complete(self, messages, *, model, **kw):
            if model != "backup":
                raise ProviderRateLimited("nope")
            return Completion(text="from backup", model=model)

    r = ResilientProvider(OnlyBackup(), retry=RetryPolicy(attempts=1),
                          fallback_models=("backup",), sleep=_nosleep)
    assert (await r.complete(MSGS, model="primary")).text == "from backup"


async def test_all_exhausted_reports_what_was_tried():
    r = ResilientProvider(Flaky(fails=99), retry=RetryPolicy(attempts=1),
                          fallback_models=("b", "c"), sleep=_nosleep)
    with pytest.raises(AllProvidersFailed) as exc:
        await r.complete(MSGS, model="a")
    assert exc.value.context["tried"] == ["a", "b", "c"]


async def test_backoff_is_bounded_and_increasing():
    policy = RetryPolicy(base_delay=1.0, max_delay=4.0, jitter=0.0)
    import random
    rng = random.Random(0)
    delays = [policy.delay_for(i, rng) for i in range(5)]
    assert delays[0] == 1.0 and delays[1] == 2.0
    assert all(d <= 4.0 for d in delays)


def test_tool_call_parsing_handles_json_string_arguments():
    calls = _parse_tool_calls([
        {"id": "c1", "function": {"name": "f", "arguments": '{"a": 1}'}}
    ])
    assert calls[0].name == "f" and calls[0].arguments == {"a": 1}


def test_tool_call_parsing_survives_malformed_arguments():
    calls = _parse_tool_calls([
        {"id": "c1", "function": {"name": "f", "arguments": "not json"}}
    ])
    assert calls[0].arguments["_raw"] == "not json"


async def _nosleep(_seconds: float) -> None:
    return None
