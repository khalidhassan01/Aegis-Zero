"""MemRL: reinforcement-weighted memory retrieval.

Episodes are ranked by a blend of semantic similarity, a learned utility
score, and recency. Utility is updated from reward signals with a bandit
style rule, so memories that actually help get surfaced more often and
memories that mislead decay out.

Final rank = w_sim * similarity + w_util * utility + w_rec * recency
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..core.models import Episode, new_id
from .store import Hit, VectorStore


@dataclass(frozen=True, slots=True)
class MemRLConfig:
    w_similarity: float = 0.60
    w_utility: float = 0.30
    w_recency: float = 0.10
    learning_rate: float = 0.25
    half_life_days: float = 21.0
    decay_per_batch: float = 0.02
    prune_below: float = -0.60
    min_similarity: float = 0.05
    candidate_multiplier: int = 4
    #: Exploration bonus (UCB1 style). A memory that has rarely been tried
    #: gets a ranking boost, so a single early lucky reward cannot lock a
    #: competitor out forever. Set to 0.0 for pure exploitation.
    exploration: float = 0.15
    #: Ceiling on the exploration bonus, so an unseen memory cannot outrank
    #: a strongly relevant one on novelty alone.
    exploration_cap: float = 0.35


@dataclass(frozen=True, slots=True)
class RankedMemory:
    episode: Episode
    similarity: float
    utility: float
    recency: float
    rank: float


class Embedder:
    """Adapts an LLM provider's embedding endpoint, with caching."""

    def __init__(
        self, provider: Any, model: str = "nomic-embed-text", cache_size: int = 512
    ) -> None:
        self.provider = provider
        self.model = model
        self._cache: dict[str, list[float]] = {}
        self._cache_size = cache_size

    async def embed_one(self, text: str) -> list[float]:
        if text in self._cache:
            return self._cache[text]
        vec = (await self.provider.embed([text], model=self.model))[0]
        if len(self._cache) >= self._cache_size:
            self._cache.pop(next(iter(self._cache)))
        self._cache[text] = vec
        return vec

    async def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.provider.embed(list(texts), model=self.model)


class MemRLEngine:
    """Retrieval, reward attribution, and consolidation over a VectorStore."""

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        config: MemRLConfig | None = None,
        clock: Any = time.time,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.cfg = config or MemRLConfig()
        self._clock = clock

    # -- write -------------------------------------------------------

    async def remember(
        self, text: str, *, kind: str = "episode", metadata: dict[str, Any] | None = None
    ) -> Episode:
        ep = Episode(
            id=new_id("ep"),
            text=text,
            kind=kind,
            created_at=self._clock(),
            metadata=metadata or {},
        )
        vec = await self.embedder.embed_one(text)
        await self.store.upsert(ep, vec)
        return ep

    # -- read --------------------------------------------------------

    def _recency(self, created_at: float) -> float:
        age_days = max(0.0, (self._clock() - created_at) / 86_400.0)
        return 0.5 ** (age_days / self.cfg.half_life_days)

    @staticmethod
    def _utility(ep: Episode) -> float:
        """Squash the learned score into 0..1."""
        return 1.0 / (1.0 + math.exp(-ep.score))

    def _exploration_bonus(self, ep: Episode, total_retrievals: int) -> float:
        """UCB1-style optimism for rarely-tried memories.

        Without this the ranking is purely greedy: whichever memory happens
        to win once accumulates utility and is shown again, so an equally
        good competitor that never got an early lucky reward is locked out
        permanently. Measured before this change: one lucky reward gave a
        memory 15 out of 15 subsequent retrievals.
        """
        if self.cfg.exploration <= 0.0:
            return 0.0
        tries = max(ep.retrievals, 0)
        bonus = self.cfg.exploration * math.sqrt(
            math.log(total_retrievals + math.e) / (tries + 1)
        )
        return min(bonus, self.cfg.exploration_cap)

    async def recall(
        self,
        query: str,
        *,
        limit: int = 6,
        kind: str | None = None,
        mark_retrieved: bool = True,
    ) -> list[RankedMemory]:
        vec = await self.embedder.embed_one(query)
        pool = max(limit * self.cfg.candidate_multiplier, limit)
        hits: list[Hit] = await self.store.search(vec, limit=pool, kind=kind)

        total_retrievals = sum(max(h.episode.retrievals, 0) for h in hits)

        ranked: list[RankedMemory] = []
        for hit in hits:
            if hit.similarity < self.cfg.min_similarity:
                continue
            util = self._utility(hit.episode)
            rec = self._recency(hit.episode.created_at)
            rank = (
                self.cfg.w_similarity * hit.similarity
                + self.cfg.w_utility * util
                + self.cfg.w_recency * rec
                + self._exploration_bonus(hit.episode, total_retrievals)
            )
            ranked.append(RankedMemory(hit.episode, hit.similarity, util, rec, rank))

        ranked.sort(key=lambda r: r.rank, reverse=True)
        top = ranked[:limit]

        if mark_retrieved:
            for item in top:
                await self.store.update(
                    replace(item.episode, retrievals=item.episode.retrievals + 1)
                )
        return top

    # -- learn -------------------------------------------------------

    async def reward(
        self, episode_id: str, signal: float, *, selected: bool = True
    ) -> Episode | None:
        """Apply a reward in [-1, 1] to one episode's utility score."""
        ep = await self.store.get(episode_id)
        if ep is None:
            return None
        clipped = max(-1.0, min(1.0, signal))
        updated = replace(
            ep,
            score=ep.score + self.cfg.learning_rate * (clipped - math.tanh(ep.score)),
            reward=ep.reward + clipped,
            selections=ep.selections + (1 if selected else 0),
        )
        await self.store.update(updated)
        return updated

    async def reward_many(self, episode_ids: Sequence[str], signal: float) -> int:
        count = 0
        for eid in episode_ids:
            if await self.reward(eid, signal) is not None:
                count += 1
        return count

    async def consolidate(self, *, prune: bool = True) -> dict[str, Any]:
        """Nightly pass: decay unused episodes and prune persistent losers."""
        episodes = await self.store.all(limit=10_000)
        decayed = pruned = 0
        for ep in episodes:
            new_score = ep.score
            if ep.retrievals > 0 and ep.selections == 0:
                new_score -= self.cfg.decay_per_batch * math.log1p(ep.retrievals)
                decayed += 1
            if prune and new_score < self.cfg.prune_below:
                await self.store.delete(ep.id)
                pruned += 1
                continue
            if new_score != ep.score:
                await self.store.update(replace(ep, score=new_score))
        return {"total": len(episodes), "decayed": decayed, "pruned": pruned}

    async def health(self) -> dict[str, Any]:
        episodes = await self.store.all(limit=10_000)
        if not episodes:
            return {"count": 0, "mean_score": 0.0, "hit_rate": 0.0, "stale": 0}
        retrieved = sum(e.retrievals for e in episodes)
        selected = sum(e.selections for e in episodes)
        cutoff = self._clock() - self.cfg.half_life_days * 4 * 86_400
        return {
            "count": len(episodes),
            "mean_score": sum(e.score for e in episodes) / len(episodes),
            "hit_rate": (selected / retrieved) if retrieved else 0.0,
            "stale": sum(1 for e in episodes if e.created_at < cutoff),
        }


# -- reward signal extraction ----------------------------------------

_POSITIVE = (
    "thanks",
    "thank you",
    "perfect",
    "correct",
    "exactly",
    "works",
    "great",
    "danke",
    "passt",
    "richtig",
    "genau",
)
_NEGATIVE = (
    "wrong",
    "no,",
    "nope",
    "incorrect",
    "broken",
    "failed",
    "not what",
    "falsch",
    "nein",
    "kaputt",
    "geht nicht",
)


def signal_from_text(text: str) -> float:
    """Heuristic reward in [-1, 1] from a user's natural-language reaction."""
    low = text.lower().strip()
    pos = sum(1 for t in _POSITIVE if t in low)
    neg = sum(1 for t in _NEGATIVE if t in low)
    if pos == neg:
        return 0.0
    total = pos + neg
    return max(-1.0, min(1.0, (pos - neg) / total))


def signal_from_outcome(*, success: bool, confidence: float = 1.0) -> float:
    """Reward derived from a verified task outcome."""
    magnitude = max(0.0, min(1.0, confidence))
    return magnitude if success else -magnitude
