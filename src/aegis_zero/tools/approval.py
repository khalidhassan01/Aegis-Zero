"""Human-in-the-loop approval gates."""

from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass
from typing import Any

from ..core.models import Risk


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    run_id: str
    tool: str
    risk: Risk
    reason: str
    arguments: dict[str, Any]


class ApprovalGate(abc.ABC):
    @abc.abstractmethod
    async def request(self, req: ApprovalRequest) -> bool:
        """Return True if the action may proceed."""


class AutoApprove(ApprovalGate):
    """Approves everything. Only appropriate for tests and sandboxes."""

    async def request(self, req: ApprovalRequest) -> bool:
        return True


class DenyAll(ApprovalGate):
    """Safe default when no human channel is configured."""

    async def request(self, req: ApprovalRequest) -> bool:
        return False


class CallbackGate(ApprovalGate):
    """Delegates to a sync or async callable, with a timeout."""

    def __init__(self, fn: Any, timeout: float = 300.0, default: bool = False) -> None:
        self.fn = fn
        self.timeout = timeout
        self.default = default

    async def request(self, req: ApprovalRequest) -> bool:
        try:
            result = self.fn(req)
            if asyncio.iscoroutine(result):
                result = await asyncio.wait_for(result, timeout=self.timeout)
            return bool(result)
        except (TimeoutError, Exception):
            return self.default


class ConsoleGate(ApprovalGate):
    """Prompts on stdin without blocking the event loop."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    async def request(self, req: ApprovalRequest) -> bool:
        prompt = (
            f"\n[approval] run={req.run_id} tool={req.tool} "
            f"risk={req.risk.value}\n  reason: {req.reason}\n"
            f"  args: {req.arguments}\n  approve? [y/N] "
        )
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(input, prompt), timeout=self.timeout
            )
        except (TimeoutError, EOFError, OSError):
            return False
        return answer.strip().lower() in ("y", "yes")
