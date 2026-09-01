"""Task routing: classify the work, rank every usable (model, key) pair.

Ranking is a weighted, explainable blend:

* capability (55%) — the benchmark score for the request's category,
* reliability (25%) — learned success rate for this exact key+model pair,
* latency fit (10%) — how close expected latency is to what the category
  wants (chat wants fast, reasoning tolerates slow),
* freshness (10%) — prefer pairs the pool has *not* been hammering, so
  concurrent requests spread out instead of tripping one rate limiter.

Hard filters run before any scoring: free-only, capability requirements
(tools / vision / structured outputs / context window), key health, and
the user's preferred/excluded model lists. The output is a ranked
``Decision`` with per-candidate ``why`` strings, so "why did you pick
that model" is always answerable with numbers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from ..core.models import Message
from .benchmarks import BenchmarkTable, is_embedding_model
from .catalog import ModelCatalog
from .keys import KeyPool
from .learning import Learner
from .types import (
    Candidate,
    Category,
    Decision,
    KeyRecord,
    KeyState,
    ModelInfo,
    key_usable,
)

#: Target latency (ms) per category for the latency-fit term.
_CATEGORY_LATENCY_MS: dict[Category, float] = {
    Category.CHAT: 2_500.0,
    Category.REASONING: 20_000.0,
    Category.CODE: 12_000.0,
    Category.VISION: 8_000.0,
    Category.LONG_CONTEXT: 30_000.0,
    Category.SAFETY: 3_000.0,
    Category.EMBEDDING: 1_000.0,
}

#: Prompt-token threshold that flips a request to LONG_CONTEXT.
_LONG_CONTEXT_TOKENS = 128_000


@dataclass(frozen=True, slots=True)
class TaskProfile:
    """What one incoming request needs, after classification."""

    category: Category
    needs_tools: bool = False
    needs_vision: bool = False
    needs_structured: bool = False
    min_context: int = 0
    why: str = ""


def classify(
    requested: str,
    messages: Sequence[Message] = (),
    *,
    tools: Sequence[dict] | None = None,
    token_estimate: int | None = None,
) -> TaskProfile:
    """Turn a model hint ("auto:code", a literal id, ...) plus the request
    shape into a TaskProfile.

    ``auto:<category>`` is explicit. A literal model id bypasses routing
    (category CHAT, no constraints). Otherwise the request is classified
    from its shape: images demand vision, tools demand tool support, and
    a huge prompt demands long-context models.
    """
    hint = (requested or "").strip()
    if hint.lower().startswith("auto:"):
        raw = hint.split(":", 1)[1].strip().lower()
        try:
            category = Category(raw)
        except ValueError:
            category = Category.REASONING
        profile = TaskProfile(category=category, why=f'explicit "{hint}"')
        if category is Category.VISION:
            profile = replace(profile, needs_vision=True)
        return profile

    if hint and hint != "auto":
        # A literal model id is an explicit user choice: route to it
        # directly (the shield still rotates keys and protects limits).
        return TaskProfile(category=Category.CHAT, why=f'literal model "{hint}"')

    # Shape-based classification for "auto".
    needs_vision = _has_image_content(messages)
    approx_tokens = (
        token_estimate
        if token_estimate is not None
        else sum(len(m.content or "") for m in messages) // 4
    )
    if needs_vision:
        return TaskProfile(
            category=Category.VISION,
            needs_vision=True,
            needs_tools=bool(tools),
            why="request contains images",
        )
    if approx_tokens >= _LONG_CONTEXT_TOKENS:
        return TaskProfile(
            category=Category.LONG_CONTEXT,
            needs_tools=bool(tools),
            min_context=_LONG_CONTEXT_TOKENS,
            why=f"~{approx_tokens // 1000}k prompt tokens",
        )
    if tools:
        return TaskProfile(
            category=Category.CODE, needs_tools=True, why="tool-calling agent step"
        )
    return TaskProfile(category=Category.CHAT, why="plain conversational turn")


def _has_image_content(messages: Sequence[Message]) -> bool:
    for msg in messages:
        content = msg.content or ""
        # OpenAI-compatible multimodal payloads embed an image_url part;
        # markdown/data-URIs are the other common convention.
        if '"image_url"' in content or "![](data:image" in content:
            return True
    return False


@dataclass(slots=True)
class RouterConfig:
    """Knobs for ranking weights and user model preferences."""

    preferred: tuple[str, ...] = ()  # tried first when healthy (exact ids)
    excluded: tuple[str, ...] = ()  # never routed to (exact or prefix)
    max_candidates: int = 8  # ladder depth per request
    weight_capability: float = 0.55
    weight_reliability: float = 0.25
    weight_latency: float = 0.10
    weight_freshness: float = 0.10


class TaskRouter:
    """Ranks candidates for a TaskProfile from catalog + pool + learner."""

    def __init__(
        self,
        catalog: ModelCatalog,
        pool: KeyPool,
        learner: Learner,
        benchmarks: BenchmarkTable,
        *,
        config: RouterConfig | None = None,
    ) -> None:
        self.catalog = catalog
        self.pool = pool
        self.learner = learner
        self.benchmarks = benchmarks
        self.config = config or RouterConfig()

    def route(
        self,
        profile: TaskProfile,
        *,
        exclude: Iterable[str] = (),
        now_keys: Mapping[str, KeyState] | None = None,
    ) -> Decision:
        """Build the ranked candidate ladder for one request.

        ``exclude`` holds model ids to skip (recently failed here) so the
        shield can walk *down* the ladder without re-attempting a dud.
        """
        excluded = set(self.config.excluded) | set(exclude)
        candidates: list[Candidate] = []

        # Preferred models keep their ranking but get a provenance tag; a
        # healthy preferred model that fits wins on the bonus below.
        preferred = set(self.config.preferred)

        for model in self._usable_models(profile, excluded):
            keys = self._usable_keys(model, now_keys)
            if not keys:
                continue
            # One candidate per (model, best key): the shield rotates to
            # other keys of the same model only on key-specific failure,
            # so the ladder stays model-diverse (better vs. rate limits).
            key = keys[0]
            score, why = self._score(model, key, profile, preferred)
            candidates.append(Candidate(model=model, key=key, score=score, why=why))

        candidates.sort(key=lambda c: (-c.score, c.model.id))
        ladder = tuple(candidates[: self.config.max_candidates])
        return Decision(category=profile.category, candidates=ladder)

    # -- internals ----------------------------------------------------------

    def _usable_models(self, profile: TaskProfile, excluded: set[str]) -> list[ModelInfo]:
        out = []
        for model in self.catalog.free_models():
            if profile.category is Category.EMBEDDING and not is_embedding_model(model.id):
                continue  # a chat model cannot serve /embeddings
            if model.id in excluded or self._matches_any(model.id, excluded):
                continue
            if not model.fits(
                needs_tools=profile.needs_tools,
                needs_vision=profile.needs_vision,
                needs_structured=profile.needs_structured,
                min_context=profile.min_context,
            ):
                continue
            if not self.pool.for_provider(model.provider):
                continue  # no key for that provider today
            out.append(model)
        return out

    @staticmethod
    def _matches_any(model_id: str, patterns: Iterable[str]) -> bool:
        base = model_id.split(":")[0]
        return any(model_id == p or base == p or base.startswith(p) for p in patterns)

    def _usable_keys(
        self, model: ModelInfo, now_keys: Mapping[str, KeyState] | None
    ) -> list[KeyRecord]:
        """Keys of this model's provider that are usable right now.

        Unprobed keys are usable: their first request is the probe.
        """
        usable: list[KeyRecord] = []
        for record in self.pool.for_provider(model.provider):
            if now_keys is not None:
                # Missing fingerprints fail closed (never attemptable).
                state = now_keys.get(record.fingerprint, KeyState.QUARANTINED)
                if not key_usable(state):
                    continue
            elif not key_usable(self.pool.health(record.fingerprint).status(self.pool.clock())):
                continue
            usable.append(record)
        return usable

    def _score(
        self,
        model: ModelInfo,
        key,
        profile: TaskProfile,
        preferred: set[str],
    ) -> tuple[float, str]:
        capability, source = self.benchmarks.explain(model, profile.category)
        reliability = self.learner.reliability(key.fingerprint, model.id)
        expected_latency = self.learner.latency(key.fingerprint, model.id)
        target = _CATEGORY_LATENCY_MS[profile.category]
        # Latency fit: 1.0 at target or faster, decaying logarithmically
        # for slow pairs (a 4x slower pair keeps ~0.5 fit).
        latency_fit = (
            1.0
            if expected_latency <= target
            else max(0.2, 1.0 - 0.5 * (expected_latency / target - 1.0))
        )
        freshness = 1.0 / (1.0 + 0.05 * self.pool.health(key.fingerprint).rate_limit_events)

        score = (
            self.config.weight_capability * (capability / 100.0)
            + self.config.weight_reliability * reliability
            + self.config.weight_latency * latency_fit
            + self.config.weight_freshness * freshness
        )
        if model.id in preferred:
            score += 0.05

        why = (
            f"bench={capability:.0f}({source}) rel={reliability:.2f} "
            f"lat={expected_latency / 1000:.1f}s fit={latency_fit:.2f}"
        )
        if model.id in preferred:
            why += " +preferred"
        return round(min(score, 1.0), 4), why

    def status_ladders(self) -> dict[str, list[dict[str, object]]]:
        """Top-3 per category for the status command."""
        out: dict[str, list[dict[str, object]]] = {}
        for category in (
            Category.CHAT,
            Category.REASONING,
            Category.CODE,
            Category.VISION,
            Category.LONG_CONTEXT,
        ):
            needs = category is Category.VISION
            profile = TaskProfile(
                category=category,
                needs_vision=needs,
                needs_tools=category is Category.CODE,
            )
            decision = self.route(profile)
            out[category.value] = [
                {
                    "model": c.model.id,
                    "score": c.score,
                    "why": c.why,
                }
                for c in decision.candidates[:3]
            ]
        return out
