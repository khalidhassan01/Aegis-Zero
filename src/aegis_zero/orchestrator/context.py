"""Context assembly: budget-aware prompt construction."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.models import Message
from ..memory.memrl import MemRLEngine, RankedMemory


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


@dataclass(slots=True)
class ContextPacket:
    system: str
    messages: list[Message] = field(default_factory=list)
    memories: list[RankedMemory] = field(default_factory=list)
    tokens: int = 0

    def to_messages(self) -> list[Message]:
        return [Message(role="system", content=self.system), *self.messages]

    @property
    def memory_ids(self) -> list[str]:
        return [m.episode.id for m in self.memories]


class ContextBuilder:
    """Builds the prompt: system instructions + recalled memory + history,
    trimmed from the middle so the goal and recent turns always survive."""

    def __init__(self, memory: MemRLEngine | None = None, *,
                 max_tokens: int = 12_000, memory_limit: int = 6,
                 keep_recent: int = 8) -> None:
        self.memory = memory
        self.max_tokens = max_tokens
        self.memory_limit = memory_limit
        self.keep_recent = keep_recent

    async def build(self, goal: str, history: Sequence[Message], *,
                    system: str, recall: bool = True,
                    extra: dict[str, Any] | None = None) -> ContextPacket:
        memories: list[RankedMemory] = []
        if recall and self.memory is not None:
            try:
                memories = await self.memory.recall(goal, limit=self.memory_limit)
            except Exception:
                memories = []

        blocks = [system]
        if memories:
            rendered = "\n".join(
                f"- [{m.episode.kind}] {m.episode.text.strip()[:400]} "
                f"(rank {m.rank:.2f})" for m in memories
            )
            blocks.append(
                "## Relevant prior knowledge\n"
                "Treat these as recollections, not ground truth. Verify before relying "
                f"on them.\n{rendered}"
            )
        if extra:
            details = "\n".join(f"- {k}: {v}" for k, v in extra.items())
            blocks.append(f"## Run context\n{details}")

        system_text = "\n\n".join(blocks)
        trimmed = self._trim(list(history), estimate_tokens(system_text))
        total = estimate_tokens(system_text) + sum(
            estimate_tokens(m.content) for m in trimmed
        )
        return ContextPacket(system=system_text, messages=trimmed,
                             memories=memories, tokens=total)

    def _trim(self, history: list[Message], used: int) -> list[Message]:
        budget = self.max_tokens - used
        if budget <= 0 or not history:
            return history[-self.keep_recent:]

        recent = history[-self.keep_recent:]
        older = history[:-self.keep_recent]
        cost = sum(estimate_tokens(m.content) for m in recent)

        kept: list[Message] = []
        for msg in reversed(older):
            c = estimate_tokens(msg.content)
            if cost + c > budget:
                break
            kept.insert(0, msg)
            cost += c

        dropped = len(older) - len(kept)
        if dropped > 0:
            note = Message(role="system",
                           content=f"[{dropped} earlier message(s) elided to fit context]")
            return [note, *kept, *recent]
        return [*kept, *recent]
