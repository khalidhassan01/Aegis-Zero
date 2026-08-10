"""Tests for MemRL learning dynamics found in the audit."""

from __future__ import annotations

import math

import pytest

from aegis_zero.memory.memrl import MemRLConfig, MemRLEngine
from aegis_zero.memory.store import InMemoryStore


class _Embedder:
    dim = 8

    async def embed_one(self, text: str):
        v = [0.0] * self.dim
        for tok in text.lower().split():
            v[hash(tok) % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def embed(self, texts):
        return [await self.embed_one(t) for t in texts]


def _engine(**kw):
    return MemRLEngine(store=InMemoryStore(), embedder=_Embedder(), config=MemRLConfig(**kw))


@pytest.mark.asyncio
async def test_one_lucky_reward_does_not_monopolise_retrieval():
    """AUDIT-10: ranking was purely greedy, so a single early reward gave a
    memory 15/15 subsequent retrievals and starved an equal competitor."""
    e = _engine(learning_rate=0.1, exploration=0.15)
    a = await e.remember("shared topic alpha", kind="fact")
    await e.remember("shared topic alpha", kind="fact")
    await e.reward(a.id, 1.0)

    winners = []
    for _ in range(15):
        hits = await e.recall("shared topic alpha", limit=1)
        wid = hits[0].episode.id
        winners.append(wid)
        await e.reward(wid, 1.0)

    a_share = winners.count(a.id) / len(winners)
    assert 0.2 < a_share < 0.9, f"monopolised: a won {a_share:.0%}"


@pytest.mark.asyncio
async def test_exploration_can_be_disabled():
    e = _engine(learning_rate=0.1, exploration=0.0)
    a = await e.remember("shared topic alpha", kind="fact")
    await e.remember("shared topic alpha", kind="fact")
    await e.reward(a.id, 1.0)
    hits = await e.recall("shared topic alpha", limit=1)
    assert hits[0].episode.id == a.id, "pure exploitation must be greedy"


@pytest.mark.asyncio
async def test_utility_score_is_bounded_by_the_tanh_update():
    """The update rule is self-limiting: score cannot grow without bound."""
    e = _engine(learning_rate=0.1)
    ep = await e.remember("bounded", kind="fact")
    for _ in range(500):
        await e.reward(ep.id, 1.0)
    final = (await e.store.get(ep.id)).score
    assert final < 5.0, f"score should saturate, got {final}"
    assert final > 1.0, "but it should still grow meaningfully"


@pytest.mark.asyncio
async def test_a_memory_can_be_unlearned_in_reasonable_time():
    """A fact that becomes false must be dislodgeable."""
    e = _engine(learning_rate=0.1)
    ep = await e.remember("the capital is Bonn", kind="fact")
    for _ in range(50):
        await e.reward(ep.id, 1.0)
    n = 0
    while (await e.store.get(ep.id)).score > 0 and n < 100:
        await e.reward(ep.id, -1.0)
        n += 1
    assert n < 30, f"took {n} negative rewards to unlearn"


@pytest.mark.asyncio
async def test_exploration_bonus_is_capped():
    e = _engine(exploration=10.0, exploration_cap=0.35)
    ep = await e.remember("never seen", kind="fact")
    bonus = e._exploration_bonus(ep, total_retrievals=1_000_000)
    assert bonus <= 0.35
