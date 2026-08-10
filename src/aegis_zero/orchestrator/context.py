"""Context assembly: budget-aware prompt construction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ..core.models import Message
from ..memory.harness import HarnessController
from ..memory.memrl import MemRLEngine, RankedMemory

#: Never emit a tail message shorter than this, or the model sees nothing useful.
_MIN_TAIL_TOKENS = 64

#: Marker appended to a message whose content had to be cut.
TRUNCATION_MARKER = "\n\n[... truncated to fit the context budget ...]"


def estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


def _truncate(msg: Message, max_tokens: int) -> Message:
    """Return ``msg`` with its content cut to roughly ``max_tokens``.

    Keeps the head and the tail, which is where instructions and the most
    recent output usually live, and marks the elision explicitly so the
    model is not misled into thinking it saw the whole thing.
    """
    budget_chars = max(max_tokens, 1) * 4
    text = msg.content or ""
    if len(text) <= budget_chars:
        return msg
    room = max(budget_chars - len(TRUNCATION_MARKER), 32)
    head = room * 2 // 3
    tail = room - head
    cut = text[:head] + TRUNCATION_MARKER + (text[-tail:] if tail > 0 else "")
    return replace(msg, content=cut)


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

    def __init__(
        self,
        memory: MemRLEngine | None = None,
        *,
        max_tokens: int = 12_000,
        memory_limit: int = 6,
        keep_recent: int = 8,
        harness_path: str | None = None,
    ) -> None:
        self.memory = memory
        self.max_tokens = max_tokens
        self.memory_limit = memory_limit
        self.keep_recent = keep_recent
        self.harness_path = harness_path

    async def build(
        self,
        goal: str,
        history: Sequence[Message],
        *,
        system: str,
        recall: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> ContextPacket:
        memories: list[RankedMemory] = []
        if recall and self.memory is not None:
            try:
                memories = await self.memory.recall(goal, limit=self.memory_limit)
            except Exception:
                memories = []

        blocks = [system]
        if memories:
            rendered = "\n".join(
                f"- [{m.episode.kind}] {m.episode.text.strip()[:400]} (rank {m.rank:.2f})"
                for m in memories
            )
            blocks.append(
                "## Relevant prior knowledge\n"
                "Treat these as recollections, not ground truth. Verify before relying "
                f"on them.\n{rendered}"
            )
        if self.harness_path:
            try:
                harness_text = HarnessController(self.harness_path).format_for_prompt()
                if harness_text:
                    blocks.append(harness_text)
            except Exception:
                # A broken harness file must never break prompt assembly.
                pass
        if extra:
            details = "\n".join(f"- {k}: {v}" for k, v in extra.items())
            blocks.append(f"## Run context\n{details}")

        system_text = "\n\n".join(blocks)

        # The system block alone can exceed the budget (many or long
        # memories). Drop memory blocks before sacrificing conversation.
        while estimate_tokens(system_text) > self.max_tokens and memories:
            memories = memories[:-1]
            rebuilt = [system]
            if memories:
                rendered = "\n".join(
                    f"- [{m.episode.kind}] {m.episode.text.strip()[:400]} (rank {m.rank:.2f})"
                    for m in memories
                )
                rebuilt.append(
                    "## Relevant prior knowledge\n"
                    "Treat these as recollections, not ground truth. Verify before relying "
                    f"on them.\n{rendered}"
                )
            if extra:
                details = "\n".join(f"- {k}: {v}" for k, v in extra.items())
                rebuilt.append(f"## Run context\n{details}")
            system_text = "\n\n".join(rebuilt)

        trimmed = self._trim(list(history), estimate_tokens(system_text))
        total = estimate_tokens(system_text) + sum(estimate_tokens(m.content) for m in trimmed)
        return ContextPacket(
            system=system_text, messages=trimmed, memories=memories, tokens=total
        )

    def _trim(self, history: list[Message], used: int) -> list[Message]:
        """Fit history into the remaining budget.

        The budget is a hard limit, not a hint. ``keep_recent`` is a
        preference for how many trailing turns to try to keep, but it never
        licenses an overrun: if even one recent message does not fit, its
        content is truncated. Callers rely on the returned packet fitting
        the model's context window.
        """
        budget = self.max_tokens - used
        if not history:
            return []
        if budget <= 0:
            # No room at all: keep the single most recent turn, truncated,
            # so the model still sees the immediate request.
            return [_truncate(history[-1], _MIN_TAIL_TOKENS)]

        # Walk the whole history newest-first and keep what fits. This is a
        # single pass, so a message can never be added twice.
        kept: list[Message] = []
        cost = 0
        for msg in reversed(history):
            c = estimate_tokens(msg.content)
            if cost + c <= budget:
                kept.insert(0, msg)
                cost += c
                continue
            # Does not fit whole. Truncate it only if it is the newest
            # message and nothing has been kept yet, so the model always
            # sees the immediate request.
            if not kept:
                room = max(budget, _MIN_TAIL_TOKENS)
                kept.insert(0, _truncate(msg, room))
                cost += room
            break

        if not kept:
            return [_truncate(history[-1], max(budget, _MIN_TAIL_TOKENS))]

        dropped = len(history) - len(kept)
        if dropped <= 0:
            return kept

        # Silent truncation misleads the model into thinking it saw the whole
        # conversation, so the elision is always announced. The note is part
        # of the budget: make room for it by shrinking the oldest kept
        # message rather than by overrunning.
        note = Message(
            role="system", content=f"[{dropped} earlier message(s) elided to fit context]"
        )
        note_cost = estimate_tokens(note.content)
        if cost + note_cost <= budget:
            return [note, *kept]

        # The note is small and its absence actively misleads the model, so
        # it is kept even in a very tight budget; the content shrinks instead.
        room = max(budget - note_cost, 16)
        while kept and cost + note_cost > budget:
            oldest = kept[0]
            oldest_cost = estimate_tokens(oldest.content)
            if len(kept) == 1:
                kept[0] = _truncate(oldest, room)
                cost = estimate_tokens(kept[0].content)
                break
            kept.pop(0)
            cost -= oldest_cost
        return [note, *kept]
