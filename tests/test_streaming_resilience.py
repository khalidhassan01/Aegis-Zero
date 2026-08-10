"""Streaming resilience: retry before first token, never after."""

from __future__ import annotations

import pytest

from aegis_zero.core.errors import AllProvidersFailed, ProviderTimeout
from aegis_zero.providers.resilient import ResilientProvider, RetryPolicy


class _Stub:
    """Fails a configurable number of times, optionally mid-stream."""

    def __init__(self, fail_times: int = 0, fail_after_tokens: int = 0):
        self.fail_times = fail_times
        self.fail_after_tokens = fail_after_tokens
        self.calls: list[str] = []

    async def stream(self, messages, *, model: str, **kw):
        self.calls.append(model)
        for i, tok in enumerate(["a", "b", "c"]):
            if self.fail_times > 0 and i >= self.fail_after_tokens:
                self.fail_times -= 1
                raise ProviderTimeout("boom")
            yield tok


async def _drain(provider, model="m"):
    return [t async for t in provider.stream([], model=model)]


@pytest.mark.asyncio
async def test_stream_retries_before_any_token_is_emitted():
    """AUDIT-12: stream() delegated straight to the inner provider, so it
    had no retry and no fallback at all."""
    inner = _Stub(fail_times=2, fail_after_tokens=0)
    p = ResilientProvider(inner, retry=RetryPolicy(attempts=3, base_delay=0), sleep=_nosleep)
    assert await _drain(p) == ["a", "b", "c"]
    assert len(inner.calls) == 3, "should have retried twice"


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_partial_output():
    """Retrying mid-stream would duplicate tokens already delivered."""
    inner = _Stub(fail_times=5, fail_after_tokens=2)
    p = ResilientProvider(inner, retry=RetryPolicy(attempts=3, base_delay=0), sleep=_nosleep)
    with pytest.raises(ProviderTimeout):
        await _drain(p)
    assert len(inner.calls) == 1, "must not retry once tokens were emitted"


@pytest.mark.asyncio
async def test_stream_falls_back_to_the_next_model():
    inner = _Stub(fail_times=2, fail_after_tokens=0)
    p = ResilientProvider(
        inner,
        retry=RetryPolicy(attempts=1, base_delay=0),
        fallback_models=("backup-1", "backup-2"),
        sleep=_nosleep,
    )
    assert await _drain(p, model="primary") == ["a", "b", "c"]
    assert inner.calls == ["primary", "backup-1", "backup-2"], (
        "one attempt per model, then fall through to the next"
    )


@pytest.mark.asyncio
async def test_stream_raises_when_every_model_fails():
    inner = _Stub(fail_times=99, fail_after_tokens=0)
    p = ResilientProvider(
        inner,
        retry=RetryPolicy(attempts=2, base_delay=0),
        fallback_models=("b1",),
        sleep=_nosleep,
    )
    with pytest.raises(AllProvidersFailed):
        await _drain(p)


async def _nosleep(_seconds: float) -> None:
    return None
