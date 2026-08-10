"""Tests for the Qdrant-backed store and the backend dispatch.

These run against Qdrant's in-memory mode (``location=":memory:"``), which
needs no standalone server, so the ``backend: qdrant`` config path is
actually verified rather than shipped blind. The ``qdrant:`` extra must be
installed for the import to resolve.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from aegis_zero.core.config import MemorySettings
from aegis_zero.memory import InMemoryStore, QdrantStore, build_store
from aegis_zero.memory.store import Episode, Hit, cosine


def _ep(text: str, **kw) -> Episode:
    kw.setdefault("kind", "fact")
    return Episode(id=None, text=text, **kw)


@pytest.mark.asyncio
async def _store() -> QdrantStore:
    s = QdrantStore(url=":memory:", collection="test_eps", vector_size=8)
    await s._ensure()
    return s


@pytest.mark.asyncio
async def test_qdrant_upsert_and_get_roundtrip():
    s = await _store()
    ep = _ep("the capital of Australia is Canberra", score=0.4, retrievals=2)
    eid = await s.upsert(ep, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
    assert eid

    got = await s.get(eid)
    assert got is not None
    assert got.text == "the capital of Australia is Canberra"
    assert got.score == pytest.approx(0.4)
    assert got.retrievals == 2


@pytest.mark.asyncio
async def test_qdrant_search_ranks_by_similarity():
    s = await _store()
    a = await s.upsert(_ep("apple fruit"), [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    await s.upsert(_ep("banana fruit"), [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    hits: list[Hit] = await s.search([0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], limit=2)
    assert hits[0].episode.id == a
    assert len(hits) == 2


@pytest.mark.asyncio
async def test_qdrant_search_can_filter_by_kind():
    s = await _store()
    await s.upsert(_ep("fact one", kind="fact"), [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    await s.upsert(
        _ep("procedure one", kind="procedure"), [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    hits = await s.search([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], limit=5, kind="fact")
    assert len(hits) == 1
    assert hits[0].episode.kind == "fact"


@pytest.mark.asyncio
async def test_qdrant_update_mutates_payload():
    s = await _store()
    eid = await s.upsert(_ep("mutable", score=0.0), [0.5] * 8)
    got = await s.get(eid)
    assert got is not None
    assert got.id is not None
    await s.update(replace(got, score=0.9))
    refreshed = await s.get(eid)
    assert refreshed is not None
    assert refreshed.score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_qdrant_get_missing_returns_none():
    s = await _store()
    assert await s.get("does-not-exist") is None


@pytest.mark.asyncio
async def test_build_store_dispatches_on_backend():
    mem = build_store(MemorySettings(backend="memory"))
    assert isinstance(mem, InMemoryStore)

    q = build_store(
        MemorySettings(backend="qdrant", url=":memory:", collection="x", vector_size=8)
    )
    assert isinstance(q, QdrantStore)
    assert q.url == ":memory:"


def test_build_store_rejects_unknown_backend():
    from aegis_zero.core.errors import ConfigError

    with pytest.raises(ConfigError):
        build_store(MemorySettings(backend="not-a-backend"))


def test_cosine_is_correct():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
