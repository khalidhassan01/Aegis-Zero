"""Deterministic in-process provider for tests, CI, and offline demos.

Supports scripted responses so orchestration logic can be tested without
any network or model server.
"""
from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.models import Completion, Message, ToolCall, Usage
from .base import LLMProvider


class EchoProvider(LLMProvider):
    """Returns scripted completions in order, then falls back to echoing."""

    name = "echo"

    def __init__(self, script: Sequence[Completion | str] | None = None,
                 vector_size: int = 768) -> None:
        self.script = list(script or [])
        self.calls: list[dict[str, Any]] = []
        self.vector_size = vector_size

    async def complete(self, messages: Sequence[Message], *, model: str,
                       **kw: Any) -> Completion:
        self.calls.append({"model": model, "messages": list(messages), **kw})
        if self.script:
            nxt = self.script.pop(0)
            if isinstance(nxt, str):
                return Completion(text=nxt, model=model,
                                  usage=Usage(len(str(messages)) // 4,
                                              len(nxt) // 4))
            return nxt
        last = messages[-1].content if messages else ""
        return Completion(text=f"echo: {last}", model=model,
                          usage=Usage(len(last) // 4, len(last) // 4))

    async def stream(self, messages: Sequence[Message], *, model: str,
                     **kw: Any) -> AsyncIterator[str]:
        result = await self.complete(messages, model=model, **kw)
        for word in result.text.split(" "):
            yield word + " "

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [((digest[i % len(digest)] / 255.0) - 0.5)
                   for i in range(self.vector_size)]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


def scripted_tool_call(name: str, arguments: dict[str, Any],
                       model: str = "test") -> Completion:
    """Helper: build a Completion that requests one tool call."""
    return Completion(text="", model=model,
                      tool_calls=(ToolCall(name=name, arguments=arguments),),
                      finish_reason="tool_calls")
