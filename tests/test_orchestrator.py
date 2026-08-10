from __future__ import annotations

import pytest

from aegis_zero.core.errors import ProviderError
from aegis_zero.core.events import EventType
from aegis_zero.core.models import Budget, Completion, Complexity, Message
from aegis_zero.memory import Embedder, InMemoryStore, MemRLEngine
from aegis_zero.observability import instrument
from aegis_zero.orchestrator import AgentEngine, EngineConfig
from aegis_zero.orchestrator.agents import (
    Subtask,
    extract_json,
    heuristic_complexity,
    parse_critique,
    parse_plan,
)
from aegis_zero.orchestrator.engine import _topological_waves
from aegis_zero.providers import EchoProvider, scripted_tool_call
from aegis_zero.tools import AutoApprove, DenyAll, PolicyEngine, ToolRegistry, default_registry

PASS = '{"verdict":"pass","confidence":0.9,"issues":[]}'


def make(script, *, registry=None, approval=None, memory=None, bus=None, **cfg):
    provider = EchoProvider(script=script)
    engine = AgentEngine(
        provider,
        registry=registry or ToolRegistry(),
        policy=PolicyEngine(resolve_host=lambda h: ["93.184.216.34"]),
        approval=approval or AutoApprove(),
        memory=memory,
        bus=bus,
        config=EngineConfig(fast_model="f", deep_model="d", **cfg),
    )
    return engine, provider


# -- parsing ---------------------------------------------------------

def test_extract_json_from_fenced_block():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_from_surrounding_prose():
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}


def test_extract_json_returns_empty_on_garbage():
    assert extract_json("no json here") == {}


def test_unparseable_critique_is_not_a_silent_pass():
    c = parse_critique(Completion(text="looks good to me!", model="m"))
    assert c.verdict == "revise" and not c.passed


def test_critique_confidence_is_clamped():
    c = parse_critique(Completion(
        text='{"verdict":"pass","confidence":9.5}', model="m"))
    assert c.confidence == 1.0


def test_plan_falls_back_to_single_subtask():
    plan = parse_plan(Completion(text="garbage", model="m"), "my goal")
    assert plan.is_single and plan.subtasks[0].goal == "my goal"


def test_plan_caps_subtasks_at_five():
    body = ",".join(f'{{"id":"s{i}","goal":"g{i}"}}' for i in range(9))
    plan = parse_plan(Completion(text=f'{{"subtasks":[{body}]}}', model="m"), "g")
    assert len(plan.subtasks) == 5


@pytest.mark.parametrize("goal,expected", [
    ("hi", Complexity.TRIVIAL),
    ("Summarise this paragraph for me please today", Complexity.SIMPLE),
])
def test_heuristic_complexity(goal, expected):
    assert heuristic_complexity(goal) is expected


# -- dependency waves ------------------------------------------------

def test_waves_group_independent_tasks():
    tasks = [Subtask("a", "A"), Subtask("b", "B"),
             Subtask("c", "C", depends_on=("a", "b"))]
    waves = _topological_waves(tasks)
    assert {t.id for t in waves[0]} == {"a", "b"}
    assert [t.id for t in waves[1]] == ["c"]


def test_waves_break_cycles_without_hanging():
    tasks = [Subtask("a", "A", depends_on=("b",)),
             Subtask("b", "B", depends_on=("a",))]
    waves = _topological_waves(tasks)
    assert sum(len(w) for w in waves) == 2


# -- run pipeline ----------------------------------------------------

async def test_trivial_goal_skips_planner():
    engine, _p = make(["the answer", PASS])
    result = await engine.run("hi")
    assert result.ok and result.answer == "the answer"
    assert result.plan.complexity is Complexity.TRIVIAL
    assert result.plan.is_single


async def test_critique_can_be_disabled():
    engine, _ = make(["only answer"], enable_critique=False)
    result = await engine.run("hi")
    assert result.answer == "only answer" and result.critique is None


async def test_tool_calling_loop_feeds_results_back():
    engine, provider = make(
        [scripted_tool_call("calculate", {"expression": "6*7"}),
         "The answer is 42", PASS],
        registry=default_registry(enable_http=False),
    )
    result = await engine.run("what is six times seven")
    assert result.tool_results[0].output == "42"
    assert "42" in result.answer
    # the tool result must have been visible to the second model call
    second_call_roles = [m.role for m in provider.calls[1]["messages"]]
    assert "tool" in second_call_roles


async def test_denied_tool_returns_error_to_model_not_crash():
    engine, _ = make(
        [scripted_tool_call("http_fetch", {"url": "file:///etc/passwd"}),
         "I could not fetch that", PASS],
        registry=default_registry(),
    )
    result = await engine.run("read the passwd file")
    assert result.ok
    assert not result.tool_results[0].ok
    assert "policy denied" in result.tool_results[0].error


async def test_approval_denial_blocks_tool():
    engine, _ = make(
        [scripted_tool_call("write_file", {"path": "/tmp/x", "content": "y"}),
         "could not write", PASS],
        registry=default_registry(), approval=DenyAll(),
    )
    result = await engine.run("write a file")
    assert "human approval denied" in result.tool_results[0].error


async def test_parallel_subtasks_execute_concurrently():
    plan = ('{"complexity":"complex","parallel":true,"subtasks":'
            '[{"id":"s1","goal":"A"},{"id":"s2","goal":"B"}]}')
    engine, _p = make([plan, "recon", "res A", "res B", "merged", PASS])
    result = await engine.run(
        "Do A and then B and also C with several steps and verify everything after"
    )
    assert len(result.plan.subtasks) == 2
    assert result.answer == "merged"


async def test_dependent_subtask_receives_upstream_output():
    plan = ('{"complexity":"complex","parallel":true,"subtasks":'
            '[{"id":"s1","goal":"A"},'
            '{"id":"s2","goal":"B","depends_on":["s1"]}]}')
    engine, provider = make([plan, "recon", "OUTPUT_FROM_S1", "res B",
                             "merged", PASS])
    await engine.run("Do A and then B and also C with steps and verify after")
    joined = "".join(m.content for c in provider.calls for m in c["messages"])
    assert "OUTPUT_FROM_S1" in joined


async def test_revision_loop_runs_on_failed_audit():
    engine, _ = make([
        "first attempt",
        '{"verdict":"revise","confidence":0.3,"issues":["missing detail"],'
        '"suggestion":"add detail"}',
        "second attempt with detail",
        PASS,
    ], max_revisions=1)
    result = await engine.run("hi")
    assert result.revisions == 1
    assert result.answer == "second attempt with detail"
    assert result.critique.passed


async def test_revision_respects_max_revisions():
    revise = '{"verdict":"revise","confidence":0.2,"issues":["x"]}'
    engine, _ = make(["a", revise, "b", revise, "c", revise], max_revisions=2)
    result = await engine.run("hi")
    assert result.revisions == 2


async def test_fail_verdict_stops_immediately():
    engine, _ = make(["bad", '{"verdict":"fail","confidence":0.9,"issues":["unsafe"]}'],
                     max_revisions=3)
    result = await engine.run("hi")
    assert result.revisions == 0 and not result.ok


async def test_step_budget_is_enforced():
    engine, _ = make(["a"] * 50)
    result = await engine.run("hi", budget=Budget(max_steps=2))
    assert not result.ok and "step budget" in result.error


async def test_token_budget_is_enforced():
    engine, _ = make(["x" * 4000] * 20)
    result = await engine.run("hi", budget=Budget(max_tokens=50))
    assert not result.ok and "token budget" in result.error


async def test_provider_failure_is_reported_not_raised():
    class Broken(EchoProvider):
        async def complete(self, *a, **kw):
            raise ProviderError("upstream down")

    engine = AgentEngine(Broken(), config=EngineConfig())
    result = await engine.run("hi")
    assert not result.ok and "upstream down" in result.error


async def test_tool_iteration_cap_forces_final_answer():
    reg = default_registry(enable_http=False)
    script = [scripted_tool_call("calculate", {"expression": "1"})] * 3
    script += ["forced final", PASS]
    engine, _ = make(script, registry=reg, max_tool_iterations=3)
    result = await engine.run("loop forever")
    assert result.answer == "forced final"
    assert len(result.tool_results) == 3


async def test_events_are_emitted_in_order():
    from aegis_zero.core.events import EventBus
    bus = EventBus()
    seen: list[EventType] = []
    bus.subscribe(lambda e: seen.append(e.type))
    engine, _ = make([scripted_tool_call("calculate", {"expression": "1"}),
                      "done", PASS],
                     registry=default_registry(enable_http=False), bus=bus)
    await engine.run("hi")
    assert seen[0] is EventType.RUN_START and seen[-1] is EventType.RUN_END
    assert EventType.TOOL_END in seen and EventType.POLICY_DECISION in seen


async def test_metrics_accumulate_from_run():
    from aegis_zero.core.events import EventBus
    bus = EventBus()
    metrics = instrument(bus)
    engine, _ = make(["done", PASS], bus=bus)
    await engine.run("hi")
    snap = metrics.snapshot()
    assert snap["runs"] == 1 and snap["llm_calls"] == 2


async def test_memory_written_on_confident_success():
    store = InMemoryStore()
    mem = MemRLEngine(store, Embedder(EchoProvider(vector_size=32), "e"))
    engine, _ = make(["good answer", PASS], memory=mem)
    await engine.run("remember this")
    assert len(await store.all()) == 1


async def test_memory_not_written_on_failure():
    store = InMemoryStore()
    mem = MemRLEngine(store, Embedder(EchoProvider(vector_size=32), "e"))
    engine, _ = make(["bad", '{"verdict":"fail","confidence":0.9,"issues":["x"]}'],
                     memory=mem)
    await engine.run("do not remember")
    assert len(await store.all()) == 0


async def test_cancellation_stops_the_run():
    from aegis_zero.core.errors import Cancelled
    from aegis_zero.core.models import RunState
    engine, _ = make(["a"] * 10)
    state = RunState()
    engine.cancel(state)
    with pytest.raises(Cancelled):
        engine._check(state, Budget())


async def test_history_is_passed_into_context():
    engine, provider = make(["ok", PASS])
    history = (Message(role="user", content="EARLIER_TURN"),)
    await engine.run("hi", history=history)
    joined = "".join(m.content for m in provider.calls[0]["messages"])
    assert "EARLIER_TURN" in joined
