"""Rate-limit shield: the layer that makes failures invisible.

Every request walks a two-dimensional ladder — best model first, and
within a model, best key first — built fresh by the router. The shield
owns what happens when an attempt misbehaves:

* 429  -> cooldown that key (honoring Retry-After / X-RateLimit-Reset),
          rotate to a sibling key of the *same* model (same capability,
          fresh quota), then down the model ladder,
* 401/403/402 -> quarantine the key (a human must fix it) and rotate,
* timeout / 5xx -> one same-candidate retry with backoff, then rotate,
* model-level rejection (400) -> skip that model entirely this request.

When the whole ladder is exhausted the shield *waits* for the earliest
cooldown inside a patience budget and re-routes once more with fresh
health before giving up. A rate limit is thereby absorbed as latency,
not surfaced as an error — "never worry about rate limits" is a
property of this loop, plus per-key pacing that avoids causing 429s in
the first place.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from ..core.errors import (
    AegisError,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    SelectorExhausted,
)
from .keys import KeyPool
from .learning import Learner
from .router import TaskProfile, TaskRouter
from .types import (
    AttemptReport,
    Candidate,
    Decision,
    KeyRecord,
    KeyState,
    ModelInfo,
    key_usable,
)

log = logging.getLogger("aegis.selector.shield")

T = TypeVar("T")

#: What one attempt of the wrapped call looks like. Raises AegisError
#: subclasses on failure; returns the provider's payload on success.
AttemptFn = Callable[[ModelInfo, KeyRecord], Awaitable[T]]


@dataclass(slots=True)
class ShieldResult:
    """What a shielded execution produced, besides the payload itself."""

    value: Any = None
    decision: Decision | None = None
    reports: list[AttemptReport] = field(default_factory=list)

    @property
    def model_id(self) -> str:
        return self.decision.model_id if self.decision else ""


@dataclass(frozen=True, slots=True)
class ShieldConfig:
    patience_s: float = 120.0  # total wait budget across wait-phases
    same_candidate_retries: int = 1  # retries before rotating on soft errors
    min_request_gap_s: float = 1.0  # per-key pacing: avoid self-inflicted 429s
    backoff_base_s: float = 0.5


class RateLimitShield:
    """Executes one logical request across the whole key/model lattice."""

    def __init__(
        self,
        pool: KeyPool,
        router: TaskRouter,
        learner: Learner,
        *,
        config: ShieldConfig | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self.pool = pool
        self.router = router
        self.learner = learner
        self.config = config or ShieldConfig()
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._last_attempt_at: dict[str, float] = {}

    async def execute(
        self,
        attempt_fn: AttemptFn,
        profile: TaskProfile,
        *,
        requested_model: str = "",
    ) -> ShieldResult:
        """Run ``attempt_fn`` against the best (model, key) pair, rotating
        transparently through every failure mode until it succeeds or the
        ladder plus patience is genuinely exhausted."""
        reports: list[AttemptReport] = []
        patience_left = self.config.patience_s
        excluded_models: set[str] = set()
        waited_rounds = 0

        while True:
            # Key health may have changed since the last pass (cooldowns
            # expired, a sibling got limited): re-route every round.
            decision = self.router.route(
                profile,
                exclude=excluded_models,
                now_keys=self._key_states(),
            )
            if not decision.candidates:
                # Nothing usable at all right now. Within patience, wait
                # for the earliest cooldown and try again.
                soonest = self.pool.earliest_cooldown_end()
                if soonest is not None and waited_rounds < 2:
                    wait_for = min(
                        max(soonest - self.pool.clock(), 0.5), max(patience_left, 0.5)
                    )
                    log.info("all candidates busy; waiting %.1fs for a cooldown", wait_for)
                    await self._sleep(wait_for)
                    patience_left -= wait_for
                    waited_rounds += 1
                    continue
                raise SelectorExhausted(
                    "no usable free model",
                    context=self._context(decision, reports),
                )

            for candidate in decision.candidates:
                outcome = await self._try_model(attempt_fn, candidate, profile, reports)
                if outcome is not None:
                    return ShieldResult(
                        value=outcome,
                        decision=self._chosen_decision(decision, candidate),
                        reports=reports,
                    )

            # Ladder walked, nothing returned: wait phase, then re-route.
            soonest = self.pool.earliest_cooldown_end()
            if soonest is not None and waited_rounds < 2 and patience_left > 0:
                wait_for = min(max(soonest - self.pool.clock(), 0.5), patience_left)
                log.info("ladder exhausted; waiting %.1fs before re-route", wait_for)
                await self._sleep(wait_for)
                patience_left -= wait_for
                waited_rounds += 1
                continue

            raise SelectorExhausted(
                "all free models exhausted",
                context=self._context(decision, reports),
            )

    # -- one model, all its keys ---------------------------------------------

    async def _try_model(
        self,
        attempt_fn: AttemptFn,
        candidate: Candidate,
        profile: TaskProfile,
        reports: list[AttemptReport],
    ) -> Any:
        """Try one model across its usable keys. None = rotate onwards."""
        model = candidate.model
        keys = [candidate.key]
        # Sibling keys of the same model: identical capability, fresh
        # quota — strictly better than degrading to a worse model.
        keys += [
            k
            for k in self.router.pool.for_provider(model.provider)
            if k.fingerprint != candidate.key.fingerprint
            and key_usable(self.pool.health(k.fingerprint).status(self.pool.clock()))
        ]

        for key in keys:
            if not key_usable(self.pool.health(key.fingerprint).status(self.pool.clock())):
                continue

            for retry in range(self.config.same_candidate_retries + 1):
                await self._pace(key.fingerprint)
                started = time.perf_counter()
                try:
                    value = await attempt_fn(model, key)
                except AegisError as exc:
                    reports.append(
                        AttemptReport(
                            model=model.id,
                            key_fingerprint=key.fingerprint,
                            outcome=_classify_error(exc),
                            latency_ms=(time.perf_counter() - started) * 1000,
                            retry_after=_retry_after_of(exc),
                            detail=str(exc)[:200],
                        )
                    )
                    self.learner.record(reports[-1])
                    action = self._absorb(exc, key)
                    self.learner.save()
                    if action is _Next.MODEL:
                        return None
                    if action is _Next.KEY:
                        break  # next key of this model
                    if retry < self.config.same_candidate_retries:
                        await self._sleep(self._backoff(retry))
                        continue
                    break  # soft error out of retries -> next key
                else:
                    latency_ms = (time.perf_counter() - started) * 1000
                    self.pool.report_success(key.fingerprint)
                    report = AttemptReport(
                        model=model.id,
                        key_fingerprint=key.fingerprint,
                        outcome="success",
                        latency_ms=latency_ms,
                    )
                    reports.append(report)
                    self.learner.record(report)
                    self.learner.save()
                    return value
        return None

    # -- failure absorption ---------------------------------------------------

    def _absorb(self, exc: AegisError, key: KeyRecord) -> str:
        """Map one failure to pool mutations and where to go next.

        Returns a :class:`_Next` constant (plain strings, kept free of
        enum machinery on the hot path).
        """
        if isinstance(exc, ProviderRateLimited):
            seconds = self.pool.report_rate_limited(
                key.fingerprint, retry_after=_retry_after_of(exc)
            )
            log.warning("key %s rate limited; cooldown %.0fs", key.label, seconds)
            return _Next.KEY
        if isinstance(exc, ProviderAuthError):
            reason = exc.message
            self.pool.report_auth_failure(key.fingerprint, reason)
            log.error("key %s quarantined: %s", key.label, reason)
            return _Next.KEY
        if isinstance(exc, (ProviderTimeout, ProviderUnavailable)):
            self.pool.report_failure(key.fingerprint)
            return _Next.RETRY
        # Model-level rejection (400, unsupported capability): no point
        # burning sibling keys of a model that cannot serve this payload.
        if isinstance(exc, ProviderError):
            self.pool.report_failure(key.fingerprint)
            return _Next.MODEL
        self.pool.report_failure(key.fingerprint)
        return _Next.KEY

    async def _pace(self, fingerprint: str) -> None:
        """Per-key request spacing so bursts cannot self-inflict a 429."""
        gap = self.config.min_request_gap_s
        if gap <= 0:
            return
        last = self._last_attempt_at.get(fingerprint, 0.0)
        now = self.pool.clock()
        wait_for = last + gap - now
        if wait_for > 0:
            await self._sleep(wait_for)
        self._last_attempt_at[fingerprint] = self.pool.clock()

    def _backoff(self, retry: int) -> float:
        raw = self.config.backoff_base_s * (2**retry)
        return raw * (1 + self._rng.uniform(-0.2, 0.2))

    def _key_states(self) -> dict[str, KeyState]:
        now = self.pool.clock()
        return {
            fp: health.status(now)
            for fp, health in (
                (r.fingerprint, self.pool.health(r.fingerprint)) for r in self.pool.records
            )
        }

    def _chosen_decision(self, decision: Decision, candidate: Candidate) -> Decision:
        from dataclasses import replace

        return replace(decision, chosen=candidate)

    def _context(self, decision: Decision, reports: list[AttemptReport]) -> dict[str, Any]:
        return {
            "category": decision.category.value,
            "ladder": [c.model.id for c in decision.candidates],
            "attempts": [
                {
                    "model": r.model,
                    "key": r.key_fingerprint,
                    "outcome": r.outcome,
                    "detail": r.detail[:120],
                }
                for r in reports[-8:]
            ],
            "pool": self.pool.snapshot(),
        }


class _Next:
    """Where the shield goes after absorbing one failure."""

    RETRY = "retry"  # same key, brief backoff
    KEY = "key"  # next key of the same model
    MODEL = "model"  # skip this model entirely


def _classify_error(exc: AegisError) -> str:
    if isinstance(exc, ProviderRateLimited):
        return "rate_limited"
    if isinstance(exc, ProviderAuthError):
        return "auth"
    if isinstance(exc, ProviderTimeout):
        return "timeout"
    if isinstance(exc, ProviderUnavailable):
        return "error"
    return "error"


def _retry_after_of(exc: AegisError) -> float | None:
    raw = exc.context.get("retry_after")
    if raw is None:
        return None
    try:
        return max(float(raw), 0.0)
    except (TypeError, ValueError):
        return None


__all__ = [
    "RateLimitShield",
    "ShieldConfig",
    "ShieldResult",
]
