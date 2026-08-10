"""Typed domain models. Pure data, no I/O, no side effects."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Risk(str, Enum):
    """Tool risk tiers, ordered."""

    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def level(self) -> int:
        return _RISK_ORDER[self]


_RISK_ORDER = {
    Risk.SAFE: 0,
    Risk.LOW: 1,
    Risk.MEDIUM: 2,
    Risk.HIGH: 3,
    Risk.CRITICAL: 4,
}


class Decision(str, Enum):
    ALLOW = "allow"
    SANITIZE = "sanitize"
    APPROVE = "approve"
    DENY = "deny"


class Complexity(str, Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: new_id("call"))


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str = ""
    name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def to_wire(self) -> dict[str, Any]:
        """Render to OpenAI-compatible chat message form."""
        out: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            out["name"] = self.name
        if self.tool_calls:
            # The OpenAI wire format requires `arguments` to be a JSON *string*,
            # not an object. Ollama and vLLM reject an object outright.
            out["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {
                        "name": c.name,
                        "arguments": json.dumps(c.arguments, ensure_ascii=False),
                    },
                }
                for c in self.tool_calls
            ]
        if self.tool_call_id:
            out["tool_call_id"] = self.tool_call_id
        return out


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    usage: Usage = field(default_factory=Usage)
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = "stop"
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class ToolResult:
    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    decision: Decision = Decision.ALLOW
    call_id: str | None = None

    def as_message(self) -> Message:
        body = str(self.output) if self.ok else f"ERROR: {self.error}"
        return Message(role="tool", content=body, name=self.tool,
                       tool_call_id=self.call_id)


@dataclass(slots=True)
class Budget:
    """Hard limits enforced by the orchestrator."""

    max_steps: int = 24
    max_tokens: int = 200_000
    max_seconds: float = 600.0
    max_tool_calls: int = 64

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RunState:
    """Mutable state for a single agent run."""

    run_id: str = field(default_factory=lambda: new_id("run"))
    goal: str = ""
    steps: int = 0
    tool_calls: int = 0
    usage: Usage = field(default_factory=Usage)
    started_at: float = field(default_factory=time.monotonic)
    cancelled: bool = False

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at


@dataclass(frozen=True, slots=True)
class Episode:
    """A memory record scored by the MemRL engine."""

    id: str
    text: str
    kind: str = "episode"
    score: float = 0.0
    retrievals: int = 0
    selections: int = 0
    reward: float = 0.0
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
