"""P6 — cite-level memory credit assignment.

The citation protocol has two evidence channels, both pinned here:

1. Declared: the Forge reply ends with ``MEMORIES USED: m1, …`` and the
   engine maps tags back to episode ids through the packet.
2. Grounded: a memory's rendered text reappears verbatim in the reply.

Reward policy: declared = full signal, grounded-only = half, neither = no
reward (not punished). Verifier-invalidated memories are excluded from
both. ``EngineConfig.citation_protocol=False`` restores the legacy coarse
reward as an ablation switch.
"""

from __future__ import annotations

import pytest

from aegis_zero.core.events import EventBus, EventType
from aegis_zero.core.models import Episode
from aegis_zero.memory import Embedder, InMemoryStore, MemRLConfig, MemRLEngine
from aegis_zero.memory.memrl import RankedMemory
from aegis_zero.orchestrator import (
    AgentEngine,
    ContextBuilder,
    grounded_ids,
    parse_citations,
)
from aegis_zero.orchestrator.engine import EngineConfig
from aegis_zero.tools import AutoApprove, PolicyEngine, default_registry

GOAL = "the canonical answer to life the universe and everything is buried here"


def _ranked(eid: str, text: str) -> RankedMemory:
    return RankedMemory(
        episode=Episode(id=eid, text=text), similarity=1.0, utility=0.5, recency=1.0, rank=1.0
    )


# -- parse_citations -------------------------------------------------


def test_parses_and_strips_citation_line():
    tags = {"m1": "ep_a", "m2": "ep_b"}
    text = "Here is the answer.\nMEMORIES USED: m1, m2"
    report = parse_citations(text, tags)
    assert report.cited_ids == ("ep_a", "ep_b")
    assert report.followed is True
    assert "MEMORIES USED" not in report.clean_text
    assert report.clean_text == "Here is the answer."


def test_citation_line_leniency():
    tags = {"m1": "ep_a", "m2": "ep_b"}
    for line in (
        "memories used: m1",
        "Memories Used - m-1",
        "[MEMORIES USED: [m1]]",
        "used memories: m1;m2",
    ):
        report = parse_citations(f"Answer body.\n{line}", tags)
        assert report.followed is True, line
        assert report.clean_text == "Answer body.", line


def test_unknown_tags_are_dropped_not_guessed():
    report = parse_citations("Body.\nMEMORIES USED: m1, m9, m2", {"m1": "ep_a", "m2": "ep_b"})
    assert report.cited_ids == ("ep_a", "ep_b")


def test_explicit_none_follows_protocol():
    report = parse_citations("Body.\nMEMORIES USED: none", {"m1": "ep_a"})
    assert report.followed is True
    assert report.cited_ids == ()


def test_missing_line_when_memories_exist_is_not_followed():
    report = parse_citations("Just an answer.", {"m1": "ep_a"})
    assert report.followed is False
    assert report.cited_ids == ()


def test_missing_line_without_memories_is_vacuously_followed():
    report = parse_citations("Just an answer.", {})
    assert report.followed is True


def test_prose_mention_mid_reply_is_not_a_citation():
    # The phrase appears inside prose, with text after it: not the protocol
    # line, so it must neither be stripped nor counted as compliance.
    text = "I used memories to build this.\nMore conclusions follow.\nMEMORIES USED: m1"
    report = parse_citations(text, {"m1": "ep_a"})
    assert report.cited_ids == ("ep_a",)
    assert "I used memories to build this." in report.clean_text


def test_unparseable_tail_counts_as_attempted():
    report = parse_citations("Body.\nMEMORIES USED: the first one maybe", {"m1": "ep_a"})
    assert report.followed is True
    assert report.cited_ids == ()


# -- grounded_ids ----------------------------------------------------


def test_verbatim_reuse_is_grounded():
    memory = _ranked("ep_a", "The router binds exclusively to tailscale0 and refuses LAN")
    answer = "Setup: the router binds exclusively to tailscale0 and refuses LAN. Done."
    assert grounded_ids(answer, [memory]) == {"ep_a"}


def test_paraphrase_is_not_grounded():
    memory = _ranked("ep_a", "The router binds exclusively to tailscale0 and refuses LAN")
    answer = "The router only listens on tailscale0; the LAN is not exposed."
    assert grounded_ids(answer, [memory]) == set()


def test_short_memory_matches_as_whole_text():
    memory = _ranked("ep_a", "the answer is forty two")
    answer = "Per my notes, the answer is forty two exactly."
    assert grounded_ids(answer, [memory]) == {"ep_a"}


def test_grounding_uses_only_the_rendered_prefix():
    # A span past the 400-character render boundary was never shown to the
    # model, so it cannot count as reuse.
    head = "visible head " * 10  # 140 chars
    tail = "unseen tail " + "x" * 400
    memory = _ranked("ep_a", head + tail)
    answer = "unseen tail " + "x" * 400
    assert grounded_ids(answer, [memory]) == set()


# -- context render --------------------------------------------------


async def test_context_renders_tags_and_protocol(provider):
    memory = MemRLEngine(
        InMemoryStore(), Embedder(provider, model="e"), MemRLConfig(min_similarity=-1.0)
    )
    await memory.remember(GOAL)
    builder = ContextBuilder(memory)
    packet = await builder.build(GOAL, [], system="SYS")
    assert "[m1]" in packet.system
    assert "MEMORIES USED" in packet.system
    assert packet.memory_tags == {"m1": packet.memories[0].episode.id}


async def test_budget_drop_retags_memories(provider):
    memory = MemRLEngine(
        InMemoryStore(), Embedder(provider, model="e"), MemRLConfig(min_similarity=-1.0)
    )
    first = await memory.remember(GOAL)
    second = await memory.remember(GOAL + " again")
    builder = ContextBuilder(memory, max_tokens=8)  # forces memory drops
    packet = await builder.build(GOAL, [], system="SYS")
    kept = len(packet.memories)
    assert kept < 2, "fixture expects at least one memory to be dropped"
    # Tags must cover exactly the survivors: no dangling m2 for a dropped
    # memory, and the mapping must point at real episode ids.
    assert set(packet.memory_tags) == {f"m{i + 1}" for i in range(kept)}
    for _tag, eid in packet.memory_tags.items():
        assert eid in {first.id, second.id}
    for i, m in enumerate(packet.memories):
        assert packet.memory_tags[f"m{i + 1}"] == m.episode.id


# -- engine end-to-end ------------------------------------------------


def _engine(provider, memory, *, citation_protocol: bool = True, bus=None) -> AgentEngine:
    return AgentEngine(
        provider,
        registry=default_registry(enable_http=False),
        policy=PolicyEngine(allow_network=False),
        approval=AutoApprove(),
        memory=memory,
        bus=bus or EventBus(),
        config=EngineConfig(
            enable_planning=False,
            enable_scout=False,
            enable_critique=True,
            enable_memory_write=False,
            citation_protocol=citation_protocol,
        ),
    )


async def _seed(provider) -> tuple[MemRLEngine, str, str]:
    """Two memories with identical text, so similarity and utility tie and
    recency decides the rank. Which episode lands on ``m1`` is *computed*
    from the same ranking the ContextBuilder will see -- never assumed --
    and returned as ``(top_id, other_id)``."""
    memory = MemRLEngine(
        InMemoryStore(), Embedder(provider, model="e"), MemRLConfig(min_similarity=-1.0)
    )
    a = await memory.remember(GOAL)
    b = await memory.remember(GOAL)
    ranked = await memory.recall(GOAL, limit=2, mark_retrieved=False)
    assert {m.episode.id for m in ranked} == {a.id, b.id}
    return memory, ranked[0].episode.id, ranked[1].episode.id


async def test_cited_memory_rewarded_uncited_memory_not(provider):
    memory, top_id, other_id = await _seed(provider)
    provider.script = [
        "One answer to rule them all.\nMEMORIES USED: m1",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    result = await _engine(provider, memory).run(GOAL)

    assert result.cited_memory_ids == [top_id]
    assert result.citation_protocol_followed is True
    score_top = (await memory.store.get(top_id)).score
    score_other = (await memory.store.get(other_id)).score
    assert score_top == pytest.approx(0.25 * 0.9), "declared citation earns the full signal"
    assert score_other == 0.0, "recalled but never evidenced: no reward, no punishment"


async def test_citation_line_never_reaches_the_user(provider):
    memory, _, _ = await _seed(provider)
    provider.script = [
        "The answer, from experience.\nMEMORIES USED: m1",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    result = await _engine(provider, memory).run(GOAL)
    assert "MEMORIES USED" not in result.answer
    assert result.answer == "The answer, from experience."


async def test_grounded_reuse_earns_half_credit(provider):
    memory, top_id, other_id = await _seed(provider)
    # The reply reuses the goal text verbatim (grounded) but declares only
    # m1: m1 earns the full signal, m2 the grounded half.
    answer = f"As I recall: {GOAL}. That is the way.\nMEMORIES USED: m1"
    provider.script = [answer, '{"verdict":"pass","confidence":0.9,"issues":[]}']
    result = await _engine(provider, memory).run(GOAL)

    assert result.cited_memory_ids == [top_id]
    assert result.grounded_memory_ids == {top_id, other_id}
    score_top = (await memory.store.get(top_id)).score
    score_other = (await memory.store.get(other_id)).score
    assert score_top == pytest.approx(0.25 * 0.9)
    assert score_other == pytest.approx(0.25 * 0.5 * 0.9), "undeclared reuse earns half"


async def test_failed_run_punishes_only_evidence(provider):
    memory, top_id, other_id = await _seed(provider)
    # Verdict fail -> one corrective attempt (max_fail_revisions=1) -> still
    # fail -> the run fails. The Forge answer deliberately avoids the memory
    # text: verbatim reuse would (correctly) ground the other memory too,
    # and this test pins that ONLY the cited memory carries the blame.
    provider.script = [
        "A wrong answer, stated with unearned certainty.\nMEMORIES USED: m1",
        '{"verdict":"fail","confidence":0.8,"issues":["wrong"]}',
        "Still wrong, and now honest about it.",
        '{"verdict":"fail","confidence":0.8,"issues":["wrong again"]}',
    ]
    result = await _engine(provider, memory).run(GOAL)
    assert result.ok is False
    assert result.revisions == 1

    score_top = (await memory.store.get(top_id)).score
    score_other = (await memory.store.get(other_id)).score
    assert score_top == pytest.approx(-0.25 * 0.8), "cited memory is penalised"
    assert score_other == 0.0, "uncited memory is not punished for a failure it did not cause"


async def test_no_protocol_no_reward_grounding_only(provider):
    memory, top_id, other_id = await _seed(provider)
    # The model ignores the protocol entirely (no line). Nothing is
    # declared; nothing is reused verbatim; nobody earns anything.
    provider.script = [
        "A wholly original answer with no reuse.",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    result = await _engine(provider, memory).run(GOAL)
    assert result.citation_protocol_followed is False
    assert (await memory.store.get(top_id)).score == 0.0
    assert (await memory.store.get(other_id)).score == 0.0
    assert result.summary()["memories_credited"] == 0


async def test_ablation_switch_restores_coarse_reward(provider):
    memory, top_id, other_id = await _seed(provider)
    provider.script = [
        "A wholly original answer with no reuse.",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    result = await _engine(provider, memory, citation_protocol=False).run(GOAL)
    assert result.cited_memory_ids == []
    assert result.citation_protocol_followed is None
    assert (await memory.store.get(top_id)).score == pytest.approx(0.25 * 0.9)
    assert (await memory.store.get(other_id)).score == pytest.approx(0.25 * 0.9)


async def test_credit_event_is_published(provider):
    memory, _top_id, _other_id = await _seed(provider)
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe(lambda e: seen.append(e.data) if e.type is EventType.MEMORY_CREDIT else None)
    provider.script = [
        f"{GOAL} verbatim once.\nMEMORIES USED: m1",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    await _engine(provider, memory, bus=bus).run(GOAL)
    credit_events = [d for d in seen if "recalled" in d]
    assert len(credit_events) == 1
    assert credit_events[0]["recalled"] == 2
    assert credit_events[0]["cited"] == 1
    assert credit_events[0]["applied"] == 2, "both credited memories' rewards landed"
    assert credit_events[0]["followed"] is True


async def test_credit_event_published_even_when_nothing_credited(provider):
    memory, _top_id, _other_id = await _seed(provider)
    # "Recalled, none evidenced" must still emit the credit event: the P6
    # fine-grained-attribution metric needs the zero cases too, not just
    # the wins.
    bus = EventBus()
    seen: list[dict] = []
    bus.subscribe(lambda e: seen.append(e.data) if e.type is EventType.MEMORY_CREDIT else None)
    provider.script = [
        "A wholly original answer with no reuse.",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    await _engine(provider, memory, bus=bus).run(GOAL)
    credit_events = [d for d in seen if "recalled" in d]
    assert len(credit_events) == 1
    assert credit_events[0]["recalled"] == 2
    assert credit_events[0]["credited"] == 0
    assert credit_events[0]["applied"] == 0
    assert credit_events[0]["followed"] is False


async def test_invalidated_memories_excluded_from_both_channels(provider):
    memory, _top_id, _other_id = await _seed(provider)
    # "2 + 2 = 77"-style hard verifier failure tombstones every recalled
    # memory; even a citation cannot earn reward after that.
    goal = "What is 2 + 2?"
    a = await memory.remember(goal)
    # Answer restates the wrong arithmetic -> verify_arithmetic hard-fails.
    provider.script = [
        "2 + 2 = 77. That is the answer.\nMEMORIES USED: m1",
        '{"verdict":"pass","confidence":0.9,"issues":[]}',
    ]
    result = await _engine(provider, memory).run(goal)
    assert a.id in result.invalidated_memory_ids
    reloaded = await memory.store.get(a.id)
    assert reloaded.deprecated is True
    assert reloaded.score <= 0.0, "tombstoned memory must not gain reward"
