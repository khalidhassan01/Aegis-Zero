"""Regression tests for temporal validity and contradiction handling (P6.5).

These pin the bi-temporal behaviour: a memory that becomes false is
deprecated (not deleted), stops ranking highly, but stays findable for
manual correction; and a newer memory with the same entity key supersedes
an older one on write.
"""

from __future__ import annotations

import math

import pytest

from aegis_zero.memory import MemRLConfig, MemRLEngine
from aegis_zero.memory.store import InMemoryStore


class _Embedder:
    dim = 8

    async def embed_one(self, text: str):
        # Deterministic embedding (no builtin hash(), which is seeded
        # per-process and would make ranking tests flaky).
        import hashlib

        v = [0.0] * self.dim
        for tok in text.lower().split():
            h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "big")
            v[h % self.dim] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    async def embed(self, texts):
        return [await self.embed_one(t) for t in texts]


def _engine(**kw):
    return MemRLEngine(store=InMemoryStore(), embedder=_Embedder(), config=MemRLConfig(**kw))


@pytest.mark.asyncio
async def test_expired_memory_ranks_below_valid_peer():
    """A fact that became false must not outrank a still-true peer."""
    e = _engine()
    old = await e.remember("the capital of X is A", metadata={"entity_key": "cap:X"})
    new = await e.remember("the capital of X is B", metadata={"entity_key": "cap:X"})
    # simulate time passing and the older fact expiring
    from dataclasses import replace

    old_ep = await e.store.get(old.id)
    await e.store.update(replace(old_ep, deprecated=True, valid_until=e._clock() - 1))
    hits = await e.recall("capital of X", limit=2)
    assert hits[0].episode.id == new.id
    # both still retrievable (reversible), but the valid one wins
    assert all(h.episode.id in (old.id, new.id) for h in hits)


@pytest.mark.asyncio
async def test_supersede_on_write_deprecates_older_same_entity():
    e = _engine()
    first = await e.remember("user lives in Berlin", metadata={"entity_key": "home"})
    second = await e.remember("user lives in Paris", metadata={"entity_key": "home"})
    first_ep = await e.store.get(first.id)
    assert first_ep.deprecated is True, "older same-entity memory should be superseded"
    second_ep = await e.store.get(second.id)
    assert second_ep.deprecated is False


@pytest.mark.asyncio
async def test_invalidate_marks_deprecated_without_deleting():
    e = _engine()
    ep = await e.remember("the server is at 10.0.0.5", metadata={"entity_key": "srv"})
    assert (await e.store.get(ep.id)).deprecated is False
    updated = await e.invalidate(ep.id, reason="verifier found wrong IP")
    assert updated is not None
    assert updated.deprecated is True
    assert await e.store.get(ep.id) is not None, "tombstoned, never deleted"
    assert updated.metadata.get("invalidated") == "verifier found wrong IP"


@pytest.mark.asyncio
async def test_invalidated_memory_still_findable_but_downranked():
    e = _engine()
    ep = await e.remember("password is hunter2", metadata={"entity_key": "pw"})
    await e.invalidate(ep.id, reason="rotated")
    hits = await e.recall("password", limit=3)
    assert any(h.episode.id == ep.id for h in hits), "still retrievable"
    # and the validity gate is < 1.0
    assert hits[0].rank < (0.60 + 0.30 + 0.10), "rank is gated by validity"


@pytest.mark.asyncio
async def test_invalidate_by_ids_deprecates_only_those():
    e = _engine()
    a = await e.remember("fact a", metadata={"entity_key": "k:a"})
    b = await e.remember("fact b", metadata={"entity_key": "k:b"})
    n = await e.invalidate_by_ids([a.id])
    assert n == 1
    assert (await e.store.get(a.id)).deprecated is True
    assert (await e.store.get(b.id)).deprecated is False


@pytest.mark.asyncio
async def test_memory_without_entity_key_is_not_superseded():
    """Without a caller-supplied key we must never guess -- no false
    deprecation of unrelated memories."""
    e = _engine()
    a = await e.remember("the sky is blue")
    b = await e.remember("grass is green")
    assert (await e.store.get(a.id)).deprecated is False
    assert (await e.store.get(b.id)).deprecated is False
