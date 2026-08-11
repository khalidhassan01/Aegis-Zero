"""P6 — coherent memory credit assignment.

When the deterministic verifier hard-fails, the engine tombstones the
recalled memories (P6.5) AND it must NOT then reward them in `_learn`.
Rewarding a memory the verifier just proved fed a wrong claim is
self-contradictory credit assignment. This module pins that invariant.
"""

from __future__ import annotations

import pytest

from aegis_zero.core.events import EventBus
from aegis_zero.memory import Embedder, InMemoryStore, MemRLEngine
from aegis_zero.orchestrator import AgentEngine
from aegis_zero.orchestrator.engine import EngineConfig
from aegis_zero.providers import EchoProvider
from aegis_zero.tools import AutoApprove, PolicyEngine, default_registry


@pytest.fixture
def provider() -> EchoProvider:
    return EchoProvider()


@pytest.fixture
def memory(provider) -> MemRLEngine:
    return MemRLEngine(InMemoryStore(), Embedder(provider, model="e"))


async def _run_with_answer(provider, memory, answer: str, *, critique: bool = True):
    """Run one engine pass.

    When ``critique`` is on (default) the deterministic verifier runs inside
    ``_critique_loop`` and a verifier hard-failure tombstones recalled
    memories. The EchoProvider returns the answer first and then a scripted
    "pass" critique, so the run is accepted and the run-end learns.
    """
    provider.script = [answer, '{"verdict":"pass","confidence":0.9,"issues":[]}']
    engine = AgentEngine(
        provider,
        registry=default_registry(enable_http=False),
        policy=PolicyEngine(allow_network=False),
        approval=AutoApprove(),
        memory=memory,
        bus=EventBus(),
        config=EngineConfig(
            enable_planning=False,
            enable_scout=False,
            enable_critique=critique,
            enable_memory_write=False,
        ),
    )
    return await engine.run("What is 2 + 2?")


async def test_invalidated_memory_is_not_rewarded(tmp_path, provider, memory):
    """A verifier-proven wrong answer must tombstone + refuse to reward the
    recalled memory (P6 coherence)."""
    # Seed a memory whose text matches the recall query (the goal) so the
    # deterministic embedder places it at similarity 1.0 and it is recalled.
    ep = await memory.remember(
        "What is 2 + 2?",
        metadata={"entity_key": "arithmetic:basic"},
    )

    # "2 + 2 = 77" triggers verify_arithmetic's hard failure (error > 1.0).
    await _run_with_answer(provider, memory, "2 + 2 = 77. That is the answer.")

    # It was invalidated (tombstoned) by the verifier.
    reloaded = await memory.store.get(ep.id)
    assert reloaded is not None
    assert reloaded.deprecated is True, "recalled memory should be tombstoned on hard failure"

    # And its utility score must NOT have been increased by _learn.
    # reward_many applies score += lr * (reward - tanh(score)); a positive
    # success signal would make score strictly greater than the start (0.0).
    # A tombstoned memory must see no positive reward, so score stays <= 0.
    assert reloaded.score <= 0.0, (
        f"invalidated memory was rewarded (score={reloaded.score}); "
        "P6 credit assignment is incoherent"
    )


async def test_successful_run_rewards_recalled_memory(tmp_path, provider, memory):
    """Sanity: a clean answer with no verifier failure still rewards memory."""
    # Seed a memory whose text equals the run goal, so it is recalled.
    ep = await memory.remember(
        "What is 2 + 2?",
        metadata={"entity_key": "arithmetic:basic"},
    )
    before = (await memory.store.get(ep.id)).score

    # A verifier-clean answer (no arithmetic claim, so the verifier passes).
    await _run_with_answer(provider, memory, "I will break this down step by step for you.")

    after = (await memory.store.get(ep.id)).score
    assert after > before, (
        f"a successful run should reward the recalled memory (after={after}, before={before})"
    )


async def test_invalidated_ids_excluded_from_result(provider, memory):
    """The result exposes which memories were invalidated (for audit/CLI)."""
    ep = await memory.remember(
        "What is 3 times 9?",
        metadata={"entity_key": "arithmetic:mul"},
    )
    result = await _run_with_answer(provider, memory, "3 * 9 = 12. Done.")
    assert ep.id in result.invalidated_memory_ids
    assert result.invalidated_memory_ids <= set(result.memory_ids)
