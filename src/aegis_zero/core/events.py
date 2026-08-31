"""Async event bus. Every meaningful state change is published here.

Streaming UIs, tracing, and cost accounting all subscribe rather than
being wired into the orchestrator.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    RUN_START = "run.start"
    RUN_END = "run.end"
    RUN_ERROR = "run.error"
    STEP_START = "step.start"
    STEP_END = "step.end"
    LLM_START = "llm.start"
    LLM_TOKEN = "llm.token"
    LLM_END = "llm.end"
    TOOL_START = "tool.start"
    TOOL_END = "tool.end"
    POLICY_DECISION = "policy.decision"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_RESULT = "approval.result"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    #: P6 cite-level attribution: which memories earned reward weight and
    #: how much, emitted once per run from the learner.
    MEMORY_CREDIT = "memory.credit"
    BUDGET_WARNING = "budget.warning"


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    run_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    at: float = field(default_factory=time.time)


Subscriber = Callable[[Event], Any]


class EventBus:
    """Fan-out bus supporting callbacks and async-iterator streams."""

    def __init__(self) -> None:
        self._subs: list[Subscriber] = []
        self._queues: list[asyncio.Queue[Event | None]] = []

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        self._subs.append(fn)
        return lambda: self._subs.remove(fn) if fn in self._subs else None

    async def publish(self, event: Event) -> None:
        for fn in list(self._subs):
            result = fn(event)
            if asyncio.iscoroutine(result):
                await result
        for q in list(self._queues):
            q.put_nowait(event)

    async def stream(self) -> AsyncIterator[Event]:
        """Consume events as they are published until ``close`` is called."""
        q: asyncio.Queue[Event | None] = asyncio.Queue()
        self._queues.append(q)
        try:
            while True:
                item = await q.get()
                if item is None:
                    return
                yield item
        finally:
            if q in self._queues:
                self._queues.remove(q)

    def close(self) -> None:
        for q in list(self._queues):
            q.put_nowait(None)


class NullBus(EventBus):
    """Drop-everything bus for tests and library embedding."""

    async def publish(self, event: Event) -> None:
        return None
