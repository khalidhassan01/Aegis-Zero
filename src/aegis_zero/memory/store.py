"""Vector store abstraction with an always-available in-process backend."""

from __future__ import annotations

import abc
import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..core.errors import MemoryError_
from ..core.models import Episode, new_id


@dataclass(frozen=True, slots=True)
class Hit:
    episode: Episode
    similarity: float


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class VectorStore(abc.ABC):
    @abc.abstractmethod
    async def upsert(self, episode: Episode, vector: Sequence[float]) -> str: ...

    @abc.abstractmethod
    async def search(
        self, vector: Sequence[float], *, limit: int = 6, kind: str | None = None
    ) -> list[Hit]: ...

    @abc.abstractmethod
    async def get(self, episode_id: str) -> Episode | None: ...

    @abc.abstractmethod
    async def update(self, episode: Episode) -> None: ...

    @abc.abstractmethod
    async def all(self, limit: int = 1000) -> list[Episode]: ...

    @abc.abstractmethod
    async def delete(self, episode_id: str) -> bool: ...

    async def count(self) -> int:
        return len(await self.all(limit=10**6))


class InMemoryStore(VectorStore):
    """Exact-search store. Correct, dependency-free, fine to a few 10k rows."""

    def __init__(self) -> None:
        self._eps: dict[str, Episode] = {}
        self._vecs: dict[str, list[float]] = {}

    async def upsert(self, episode: Episode, vector: Sequence[float]) -> str:
        eid = episode.id or new_id("ep")
        stored = episode if episode.id else replace(episode, id=eid)
        self._eps[eid] = stored
        self._vecs[eid] = list(vector)
        return eid

    async def search(
        self, vector: Sequence[float], *, limit: int = 6, kind: str | None = None
    ) -> list[Hit]:
        scored = [
            Hit(ep, cosine(vector, self._vecs.get(eid, [])))
            for eid, ep in self._eps.items()
            if kind is None or ep.kind == kind
        ]
        scored.sort(key=lambda h: h.similarity, reverse=True)
        return scored[:limit]

    async def get(self, episode_id: str) -> Episode | None:
        return self._eps.get(episode_id)

    async def update(self, episode: Episode) -> None:
        if episode.id not in self._eps:
            raise MemoryError_("episode not found", context={"id": episode.id})
        self._eps[episode.id] = episode

    async def all(self, limit: int = 1000) -> list[Episode]:
        return list(self._eps.values())[:limit]

    async def delete(self, episode_id: str) -> bool:
        self._vecs.pop(episode_id, None)
        return self._eps.pop(episode_id, None) is not None


class QdrantStore(VectorStore):
    """Qdrant-backed store. Imported lazily so Qdrant stays optional."""

    def __init__(
        self,
        url: str = "http://127.0.0.1:6333",
        collection: str = "aegis_episodes",
        vector_size: int = 768,
        client: Any = None,
    ) -> None:
        self.url = url
        self.collection = collection
        self.vector_size = vector_size
        self._client = client
        self._ready = False

    async def _ensure(self) -> Any:
        if self._client is None:
            try:
                from qdrant_client import AsyncQdrantClient
            except ImportError as exc:
                raise MemoryError_("qdrant-client not installed") from exc
            if self.url in (":memory:", "memory", ":in-memory:"):
                self._client = AsyncQdrantClient(location=":memory:")
            else:
                self._client = AsyncQdrantClient(url=self.url)
        if not self._ready:
            from qdrant_client.models import Distance, VectorParams

            existing = await self._client.get_collections()
            names = {c.name for c in existing.collections}
            if self.collection not in names:
                await self._client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(
                        size=self.vector_size, distance=Distance.COSINE
                    ),
                )
            self._ready = True
        return self._client

    @staticmethod
    def _payload(ep: Episode) -> dict[str, Any]:
        return {
            "text": ep.text,
            "kind": ep.kind,
            "score": ep.score,
            "retrievals": ep.retrievals,
            "selections": ep.selections,
            "reward": ep.reward,
            "created_at": ep.created_at,
            "metadata": ep.metadata,
        }

    @staticmethod
    def _episode(pid: str, payload: dict[str, Any]) -> Episode:
        return Episode(
            id=str(pid),
            text=payload.get("text", ""),
            kind=payload.get("kind", "episode"),
            score=float(payload.get("score", 0.0)),
            retrievals=int(payload.get("retrievals", 0)),
            selections=int(payload.get("selections", 0)),
            reward=float(payload.get("reward", 0.0)),
            created_at=float(payload.get("created_at", time.time())),
            metadata=payload.get("metadata") or {},
        )

    async def upsert(self, episode: Episode, vector: Sequence[float]) -> str:
        from qdrant_client.models import PointStruct

        client = await self._ensure()
        eid = episode.id or new_id("ep")
        await client.upsert(
            collection_name=self.collection,
            points=[
                PointStruct(
                    id=_uuid_of(eid),
                    vector=list(vector),
                    payload={**self._payload(episode), "eid": eid},
                )
            ],
        )
        return eid

    async def search(
        self, vector: Sequence[float], *, limit: int = 6, kind: str | None = None
    ) -> list[Hit]:
        client = await self._ensure()
        flt = None
        if kind:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            flt = Filter(must=[FieldCondition(key="kind", match=MatchValue(value=kind))])
        # qdrant-client >= 1.10 renamed ``search`` to ``query_points``; the
        # old method was removed in 1.19, so use the current API.
        try:
            resp = await client.query_points(
                collection_name=self.collection,
                query=list(vector),
                limit=limit,
                query_filter=flt,
                with_payload=True,
            )
        except AttributeError:
            # Fall back for very old clients that still expose ``search``.
            found = await client.search(
                collection_name=self.collection,
                query_vector=list(vector),
                limit=limit,
                query_filter=flt,
            )
            return [
                Hit(
                    self._episode((p.payload or {}).get("eid", p.id), p.payload or {}),
                    float(p.score),
                )
                for p in found
            ]
        points = resp.points if hasattr(resp, "points") else resp
        return [
            Hit(
                self._episode((p.payload or {}).get("eid", p.id), p.payload or {}),
                float(p.score),
            )
            for p in points
        ]

    async def get(self, episode_id: str) -> Episode | None:
        client = await self._ensure()
        pts = await client.retrieve(collection_name=self.collection, ids=[_uuid_of(episode_id)])
        if not pts:
            return None
        return self._episode(episode_id, pts[0].payload or {})

    async def update(self, episode: Episode) -> None:
        client = await self._ensure()
        await client.set_payload(
            collection_name=self.collection,
            payload=self._payload(episode),
            points=[_uuid_of(episode.id)],
        )

    async def all(self, limit: int = 1000) -> list[Episode]:
        client = await self._ensure()
        points, _ = await client.scroll(
            collection_name=self.collection, limit=limit, with_payload=True
        )
        return [
            self._episode((p.payload or {}).get("eid", p.id), p.payload or {}) for p in points
        ]

    async def delete(self, episode_id: str) -> bool:
        client = await self._ensure()
        await client.delete(
            collection_name=self.collection, points_selector=[_uuid_of(episode_id)]
        )
        return True


def _uuid_of(eid: str) -> str:
    """Deterministic UUID5 so string ids work with Qdrant's id constraints."""
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"aegis://{eid}"))
