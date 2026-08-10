"""Engine integration tests for the Continual Harness.

Verifies two things without needing a real LLM:
  * ContextBuilder injects harness entries as SUPPLEMENTAL context without
    mutating the immutable base system prompt.
  * The engine applies a grounded refinement at run end when the outcome is
    verified, and persists it to the harness path.
"""

from __future__ import annotations

import pytest

from aegis_zero.core.events import EventBus
from aegis_zero.core.models import Budget
from aegis_zero.memory import Embedder, InMemoryStore, MemRLEngine
from aegis_zero.memory.harness import HarnessController
from aegis_zero.orchestrator import AgentEngine
from aegis_zero.orchestrator.context import ContextBuilder
from aegis_zero.providers import EchoProvider
from aegis_zero.tools import AutoApprove, PolicyEngine, default_registry


@pytest.fixture
def provider():
    return EchoProvider()


@pytest.fixture
def memory(provider):
    return MemRLEngine(InMemoryStore(), Embedder(provider, model="e"))


async def test_context_builder_injects_harness_supplementally(tmp_path, memory):
    harness_path = tmp_path / "harness_state.json"
    ctrl = HarnessController(harness_path)
    from aegis_zero.memory.harness import RefinementEdit, RefinementProposal

    ctrl.apply(
        RefinementProposal(
            summary="s",
            rationale="r",
            expected_outcome="o",
            edits=[RefinementEdit(action="create", kind="memory", title="pref", content="Be terse.")],
        ),
        scope="global",
    )

    base = "BASE SYSTEM PROMPT (immutable)"
    builder = ContextBuilder(memory, harness_path=str(harness_path), memory_limit=4)
    packet = await builder.build("do the thing", [], system=base, recall=False)

    # Base prompt untouched...
    assert packet.system.startswith(base)
    # ...and harness entries appended as supplemental context.
    assert "Continual Harness State" in packet.system
    assert "Be terse." in packet.system


async def test_engine_auto_refines_on_verified_run(tmp_path, provider, memory):
    harness_path = tmp_path / "harness_state.json"
    engine = AgentEngine(
        provider,
        registry=default_registry(enable_http=False),
        policy=PolicyEngine(allow_network=False),
        approval=AutoApprove(),
        memory=memory,
        context=ContextBuilder(memory, harness_path=str(harness_path), memory_limit=4),
        bus=EventBus(),
        config=__import__("aegis_zero.orchestrator.engine", fromlist=["EngineConfig"]).EngineConfig(
            enable_planning=False, enable_critique=False, enable_scout=False, enable_memory_write=False
        ),
    )
    # EchoProvider returns the goal as the answer, so the run "succeeds" and
    # passes the (empty) verifier -> grounded extraction should fire.
    result = await engine.run("Summarize the deploy run")
    # A grounded lesson was persisted.
    ctrl = HarnessController(harness_path)
    memories = ctrl.state.entries["memory"]
    assert memories, "expected a grounded lesson to be extracted and persisted"
    assert any("[verified]" in e.content for e in memories.values())
