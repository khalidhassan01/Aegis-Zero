"""Regression tests for defects found in the architecture audit.

Each test names the bug it pins down. See docs/AUDIT.md for the analysis.
"""

from __future__ import annotations

import pytest

from aegis_zero.core.models import Decision, Message
from aegis_zero.orchestrator.agents import Subtask
from aegis_zero.orchestrator.context import (
    TRUNCATION_MARKER,
    ContextBuilder,
    estimate_tokens,
)
from aegis_zero.orchestrator.engine import _topological_waves, normalize_subtasks
from aegis_zero.tools.policy import PolicyEngine

# --------------------------------------------------------------- planning


def test_duplicate_subtask_ids_do_not_lose_work():
    """AUDIT-1: pending was a dict keyed on id, so a duplicate id silently
    discarded an entire subtask."""
    dup = [Subtask(id="s1", goal="first"), Subtask(id="s1", goal="second")]
    waves = _topological_waves(dup)
    goals = [t.goal for w in waves for t in w]
    assert sorted(goals) == ["first", "second"]
    ids = [t.id for w in waves for t in w]
    assert len(set(ids)) == 2, "ids must be made unique"


def test_dependency_on_nonexistent_task_is_dropped():
    """AUDIT-2: `d not in pending` treated a typo'd dependency as satisfied,
    which happened to work but hid malformed plans. Now it is dropped."""
    t = Subtask(id="s1", goal="g", depends_on=("s99",))
    [fixed] = normalize_subtasks([t])
    assert fixed.depends_on == ()


def test_self_dependency_is_removed():
    """AUDIT-3: a task depending on itself is unsatisfiable."""
    [fixed] = normalize_subtasks([Subtask(id="s1", goal="g", depends_on=("s1",))])
    assert fixed.depends_on == ()


def test_dependency_cycle_is_broken_deterministically():
    """AUDIT-4: the cycle-breaker picked an arbitrary dict entry, so plan
    execution order was not reproducible."""
    a = Subtask(id="b", goal="B", depends_on=("a",))
    b = Subtask(id="a", goal="A", depends_on=("b",))
    first = [t.id for w in _topological_waves([a, b]) for t in w]
    second = [t.id for w in _topological_waves([b, a]) for t in w]
    assert first == second, "cycle breaking must be order-independent"
    assert first[0] == "a", "lowest id runs first"


def test_all_subtasks_appear_exactly_once():
    tasks = [
        Subtask(id="a", goal="A"),
        Subtask(id="b", goal="B", depends_on=("a",)),
        Subtask(id="c", goal="C", depends_on=("a",)),
        Subtask(id="d", goal="D", depends_on=("b", "c")),
    ]
    flat = [t.id for w in _topological_waves(tasks) for t in w]
    assert sorted(flat) == ["a", "b", "c", "d"]
    assert flat.index("a") < flat.index("b")
    assert flat.index("b") < flat.index("d")


# --------------------------------------------------------------- context


@pytest.mark.asyncio
async def test_context_budget_is_a_hard_limit():
    """AUDIT-5: the token budget was advisory. A 100-token budget returned
    4012 tokens -- a 40x overrun that would exceed the model's window."""
    cb = ContextBuilder(memory=None, max_tokens=100, keep_recent=4)
    history = [Message(role="user", content="x" * 4000) for _ in range(10)]
    packet = await cb.build("goal", history, system="sys")
    assert packet.tokens <= 100, f"budget overrun: {packet.tokens} > 100"


@pytest.mark.asyncio
async def test_oversized_single_message_is_truncated_not_passed_through():
    """AUDIT-6: one huge message bypassed trimming entirely."""
    cb = ContextBuilder(memory=None, max_tokens=200, keep_recent=1)
    huge = [Message(role="user", content="y" * 100_000)]
    packet = await cb.build("g", huge, system="s")
    assert packet.tokens < 1000
    assert TRUNCATION_MARKER in packet.messages[0].content


@pytest.mark.asyncio
async def test_trim_never_duplicates_messages():
    """AUDIT-7: the fix's first draft returned `[*kept, *recent]`, emitting
    the recent turns twice."""
    cb = ContextBuilder(memory=None, max_tokens=100_000, keep_recent=3)
    history = [Message(role="user", content=f"m{i}") for i in range(10)]
    packet = await cb.build("g", history, system="s")
    contents = [m.content for m in packet.messages if m.role == "user"]
    assert len(contents) == len(set(contents)), "no message may appear twice"


@pytest.mark.asyncio
async def test_keep_recent_does_not_override_the_budget():
    cb = ContextBuilder(memory=None, max_tokens=10, keep_recent=6)
    history = [Message(role="user", content="z" * 4000) for _ in range(10)]
    packet = await cb.build("g", history, system="s")
    conversation = [m for m in packet.messages if m.role == "user"]
    assert len(conversation) == 1, "cannot keep 6 turns in a 10-token budget"
    assert any("elided" in m.content for m in packet.messages)


@pytest.mark.asyncio
async def test_empty_history_returns_no_messages():
    cb = ContextBuilder(memory=None, max_tokens=100, keep_recent=3)
    packet = await cb.build("g", [], system="s")
    assert packet.messages == []


def test_estimate_tokens_is_monotonic():
    assert estimate_tokens("a" * 400) > estimate_tokens("a" * 40)


# -------------------------------------------------------------- security


def test_nul_byte_in_path_is_rejected_not_crashing():
    """AUDIT-8: Path.resolve() raises ValueError on a NUL byte, which
    propagated out of policy evaluation and aborted the run."""
    p = PolicyEngine()
    ok, why = p.check_path("/tmp/ok\x00/etc/shadow")
    assert ok is False
    assert "NUL" in why


def test_nul_byte_does_not_crash_full_decide():
    p = PolicyEngine()
    verdict = p.decide("read_file", {"path": "/tmp/x\x00/etc/shadow"})
    assert verdict.decision is Decision.DENY


def test_percent_encoded_traversal_is_decoded_before_checking():
    """AUDIT-9: %2e%2e%2f smuggled separators past the traversal check."""
    p = PolicyEngine()
    ok, why = p.check_path("%2f%65%74%63%2fshadow")  # /etc/shadow
    assert ok is False, f"expected deny, got allow ({why})"


def test_encoded_nul_byte_is_rejected():
    p = PolicyEngine()
    ok, _ = p.check_path("/tmp/ok%00/etc/shadow")
    assert ok is False


@pytest.mark.parametrize(
    "path",
    ["/etc/shadow", "/proc/self/environ", "/etc/sudoers", "/home/u/.ssh/id_rsa"],
)
def test_protected_paths_still_blocked(path):
    p = PolicyEngine()
    ok, _ = p.check_path(path)
    assert ok is False


def test_ordinary_paths_still_allowed():
    p = PolicyEngine()
    ok, _ = p.check_path("notes.txt")
    assert ok is True
