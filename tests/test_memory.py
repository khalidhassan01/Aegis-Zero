from __future__ import annotations

import pytest

from aegis_zero.memory import (
    Embedder,
    InMemoryStore,
    MemRLConfig,
    MemRLEngine,
    signal_from_outcome,
    signal_from_text,
)
from aegis_zero.memory.store import cosine
from aegis_zero.providers import EchoProvider


@pytest.fixture
def engine():
    return MemRLEngine(InMemoryStore(), Embedder(EchoProvider(vector_size=64), "e"))


def test_cosine_bounds():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([], [1]) == 0.0


async def test_remember_then_recall(engine):
    await engine.remember("Morocco's capital is Rabat")
    hits = await engine.recall("Morocco's capital is Rabat")
    assert hits and "Rabat" in hits[0].episode.text


async def test_recall_increments_retrieval_count(engine):
    ep = await engine.remember("fact one")
    await engine.recall("fact one")
    assert (await engine.store.get(ep.id)).retrievals == 1


async def test_reward_raises_utility_score(engine):
    ep = await engine.remember("useful thing")
    updated = await engine.reward(ep.id, 1.0)
    assert updated.score > ep.score
    assert updated.selections == 1


async def test_negative_reward_lowers_score(engine):
    ep = await engine.remember("bad thing")
    assert (await engine.reward(ep.id, -1.0)).score < 0


async def test_reward_is_clipped(engine):
    ep = await engine.remember("x")
    a = await engine.reward(ep.id, 50.0)
    assert a.reward == 1.0


async def test_reward_on_missing_episode_returns_none(engine):
    assert await engine.reward("ep_nonexistent", 1.0) is None


async def test_ranking_prefers_rewarded_memory():
    store = InMemoryStore()
    eng = MemRLEngine(store, Embedder(EchoProvider(vector_size=64), "e"),
                      MemRLConfig(w_similarity=0.0, w_utility=1.0, w_recency=0.0,
                                  min_similarity=-1.0))
    weak = await eng.remember("alpha")
    strong = await eng.remember("beta")
    await eng.reward(strong.id, 1.0)
    await eng.reward(weak.id, -1.0)
    ranked = await eng.recall("anything", limit=2)
    assert ranked[0].episode.id == strong.id


async def test_recency_decays(engine):
    now = 1_000_000.0
    engine._clock = lambda: now
    fresh = engine._recency(now)
    old = engine._recency(now - 21 * 86400)
    assert fresh == pytest.approx(1.0)
    assert old == pytest.approx(0.5, abs=0.01)


async def test_consolidate_prunes_persistent_losers():
    store = InMemoryStore()
    eng = MemRLEngine(store, Embedder(EchoProvider(vector_size=64), "e"),
                      MemRLConfig(prune_below=-0.1))
    ep = await eng.remember("junk")
    await eng.reward(ep.id, -1.0, selected=False)
    stats = await eng.consolidate()
    assert stats["pruned"] == 1
    assert await store.get(ep.id) is None


async def test_consolidate_decays_retrieved_but_unselected():
    store = InMemoryStore()
    eng = MemRLEngine(store, Embedder(EchoProvider(vector_size=64), "e"))
    ep = await eng.remember("meh")
    await eng.recall("meh")
    stats = await eng.consolidate(prune=False)
    assert stats["decayed"] == 1
    assert (await store.get(ep.id)).score < 0


async def test_health_reports_counts(engine):
    await engine.remember("a")
    await engine.remember("b")
    health = await engine.health()
    assert health["count"] == 2


@pytest.mark.parametrize("text,sign", [
    ("thanks, that works perfectly", 1),
    ("no, that is wrong and broken", -1),
    ("das ist falsch", -1),
    ("danke, genau richtig", 1),
    ("what is the weather", 0),
])
def test_text_signals(text, sign):
    value = signal_from_text(text)
    assert (value > 0) == (sign > 0)
    assert (value < 0) == (sign < 0)


def test_outcome_signal_scales_with_confidence():
    assert signal_from_outcome(success=True, confidence=0.5) == 0.5
    assert signal_from_outcome(success=False, confidence=1.0) == -1.0


async def test_embedder_caches(engine):
    await engine.embedder.embed_one("same")
    await engine.embedder.embed_one("same")
    assert len(engine.embedder._cache) == 1
