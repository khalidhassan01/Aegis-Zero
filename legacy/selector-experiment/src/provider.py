"""SelectorProvider: the selector as a drop-in LLMProvider.

The engine keeps calling ``complete(messages, model="...")`` exactly as
before. What changes is what the model id means:

* ``auto`` — classify this request by its shape and route to the best
  free model for it,
* ``auto:<category>`` — explicit category (the engine config maps its
  roles onto these: fast -> ``auto:chat``, deep -> ``auto:reasoning``,
  code -> ``auto:code``),
* a literal model id — user's explicit choice; the shield still rotates
  keys and absorbs rate limits around it.

Streaming gets the same protection with one honest limitation, shared
with ``ResilientProvider``: a stream can only be retried *before* the
first token reaches the caller; after that, retrying would duplicate
output, so the error propagates instead.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.config import Settings
from ..core.errors import AegisError, SelectorExhausted
from ..core.models import Completion, Message
from ..providers.base import LLMProvider
from ..providers.openai_compat import OpenAICompatProvider
from .benchmarks import BenchmarkTable, load_overrides, seed_summary
from .catalog import ModelCatalog, refresh_catalog
from .keys import KeyPool, discover_keys
from .learning import Learner
from .router import RouterConfig, TaskProfile, TaskRouter, classify
from .shield import RateLimitShield, ShieldConfig, ShieldResult
from .types import Category, KeyState, ModelInfo, key_usable

log = logging.getLogger("aegis.selector")


class SelectorProvider(LLMProvider):
    """Routes every call through pool -> catalog -> benchmarks -> shield."""

    name = "selector"

    def __init__(
        self,
        settings: Settings,
        *,
        catalog: ModelCatalog | None = None,
        client_factory: Any = None,
    ) -> None:
        sel = settings.selector
        self.settings = settings
        records = discover_keys(_selector_env(), sel.keys_file, allow_paid=sel.allow_paid)
        self.pool = KeyPool(records)
        self.learner = Learner(sel.state_path)
        try:
            overrides = load_overrides(sel.benchmarks_file or None)
        except ValueError as exc:
            log.warning("benchmark overrides unreadable: %s", exc)
            overrides = {}
        self.benchmarks = BenchmarkTable(overrides)
        self.catalog = catalog or ModelCatalog.from_seed()
        self.router = TaskRouter(
            self.catalog,
            self.pool,
            self.learner,
            self.benchmarks,
            config=RouterConfig(
                preferred=tuple(sel.preferred),
                excluded=tuple(sel.excluded),
                max_candidates=sel.max_candidates,
            ),
        )
        self.shield = RateLimitShield(
            self.pool,
            self.router,
            self.learner,
            config=ShieldConfig(
                patience_s=sel.patience_s,
                min_request_gap_s=sel.min_request_gap_s,
            ),
        )
        self._client_factory = client_factory
        self._per_key: dict[str, OpenAICompatProvider] = {}
        self._embed_provider: OpenAICompatProvider | None = None
        self._refreshed = False

    # -- lifecycle ----------------------------------------------------------

    async def _ensure_catalog(self) -> None:
        """Fetch/refresh the live catalog once per process lifetime."""
        if self._refreshed:
            return
        self._refreshed = True
        if not self.settings.selector.refresh_on_start:
            return
        try:
            import httpx

            client = httpx.AsyncClient(timeout=30.0)
        except ImportError:  # pragma: no cover - httpx is a hard dependency
            return
        try:
            catalog, diff = await refresh_catalog(
                client,
                self.settings.selector.cache_path,
                ttl_s=self.settings.selector.cache_ttl_hours * 3600,
                declared=(self.pool.records and tuple(self.pool.records)) or (),
            )
        finally:
            await client.aclose()
        self.catalog = catalog
        self.router.catalog = catalog
        if diff.get("added") or diff.get("removed"):
            log.info(
                "catalog refresh: %d new, %d gone",
                len(diff.get("added") or []),
                len(diff.get("removed") or []),
            )

    async def aclose(self) -> None:
        for provider in self._per_key.values():
            await provider.aclose()
        self._per_key.clear()
        self.learner.save()

    # -- inspection (CLI: `aegis selector status` / `pick`) -----------------

    async def status(self) -> dict[str, Any]:
        """Everything an operator needs on one screen. Never a secret.

        Keys appear as provider/fingerprint labels; learning evidence is
        keyed the same way. Safe to paste into a terminal or an issue.
        """
        await self._ensure_catalog()
        free = self.catalog.free_models()
        return {
            "pool": self.pool.snapshot(),
            "catalog": {
                "source": self.catalog.source,
                "models": len(self.catalog.models),
                "free_models": len(free),
            },
            "benchmarks": seed_summary(),
            "ladders": self.router.status_ladders(),
            "learning": self.learner.snapshot(),
        }

    async def pick(self, category: str = "chat") -> dict[str, Any] | None:
        """The best free (model, key) pair for a category, without sending.

        Returns None when nothing is usable right now (empty pool, or
        every key cooling down). ``why`` carries the scoring story so the
        pick is never a black box.
        """
        await self._ensure_catalog()
        cat = Category(str(category).strip().lower())
        profile = TaskProfile(
            category=cat,
            needs_vision=cat is Category.VISION,
            needs_tools=cat is Category.CODE,
            why="explicit pick",
        )
        decision = self.router.route(profile, now_keys=self._key_states())
        if not decision.candidates:
            return None
        top = decision.candidates[0]
        return {
            "model": top.model.id,
            "score": top.score,
            "why": top.why,
            "key": top.key.label,
            "ladder": [c.model.id for c in decision.candidates],
        }

    # -- LLMProvider API ----------------------------------------------------

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str = "auto",
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Completion:
        await self._ensure_catalog()
        profile = classify(model, messages, tools=tools)
        tools_payload: list[dict[str, Any]] | None = list(tools) if tools else None

        async def attempt(m: ModelInfo, key: Any) -> Completion:
            inner = self._provider_for(key)
            return await inner.complete(
                messages,
                model=m.id,
                tools=tools_payload,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        result = await self.shield.execute(attempt, profile, requested_model=model)
        value: Completion = result.value
        if result.decision is not None and result.decision.chosen is not None:
            log.info(
                "routed %s -> %s via %s (%s)",
                model,
                result.decision.chosen.model.id,
                result.decision.chosen.key.label,
                result.decision.chosen.why,
            )
        return value

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str = "auto",
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Shielded streaming: rotate keys/models until first token."""
        await self._ensure_catalog()
        profile = classify(model, messages)

        decision = self.router.route(profile, now_keys=self._key_states())
        for candidate in decision.candidates:
            keys = [candidate.key] + [
                k
                for k in self.pool.for_provider(candidate.model.provider)
                if k.fingerprint != candidate.key.fingerprint
                and key_usable(self.pool.health(k.fingerprint).status(self.pool.clock()))
            ]
            for key in keys:
                emitted = False
                try:
                    inner = self._provider_for(key)
                    agen = inner.stream(
                        messages,
                        model=candidate.model.id,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    async for piece in agen:
                        emitted = True
                        yield piece
                    self.pool.report_success(key.fingerprint)
                    return
                except AegisError as exc:
                    if emitted:
                        raise
                    self._absorb_stream_failure(exc, key)
        raise SelectorExhausted(
            "all free models exhausted (stream)",
            context={"ladder": [c.model.id for c in decision.candidates]},
        )

    async def embed(self, texts: Sequence[str], *, model: str = "auto") -> list[list[float]]:
        """Route embeddings to the best free embedding model; fall back
        to the configured local endpoint when the free pool has none
        (today it never does — free embedders are rare)."""
        await self._ensure_catalog()
        profile = TaskProfile(category=Category.EMBEDDING, why="embeddings")

        async def attempt(m: ModelInfo, key: Any) -> list[list[float]]:
            inner = self._provider_for(key)
            return await inner.embed(texts, model=m.id)

        try:
            result = await self.shield.execute(attempt, profile)
            return result.value
        except SelectorExhausted:
            fallback = self._embed_fallback()
            sel = self.settings.selector
            return await fallback.embed(texts, model=sel.embed_fallback_model)

    # -- internals ----------------------------------------------------------

    def _provider_for(self, key: Any) -> OpenAICompatProvider:
        """One inner OpenAI-compat client per key (per base_url+secret)."""
        cached = self._per_key.get(key.fingerprint)
        if cached is None:
            cached = OpenAICompatProvider(
                base_url=key.base_url,
                api_key=key.secret,
                timeout=self.settings.provider.timeout,
                client=self._client_factory(key) if self._client_factory else None,
            )
            self._per_key[key.fingerprint] = cached
        return cached

    def _embed_fallback(self) -> OpenAICompatProvider:
        sel = self.settings.selector
        cached = self._embed_provider
        if cached is None:
            # The factory is called with None: the fallback endpoint has
            # no key record. A factory that only accepts key records must
            # treat None as "build me a bare client".
            cached = OpenAICompatProvider(
                base_url=sel.embed_fallback_base_url,
                api_key="",
                timeout=self.settings.provider.timeout,
                client=self._client_factory(None) if self._client_factory else None,
            )
            self._embed_provider = cached
        return cached

    def _key_states(self) -> dict[str, KeyState]:
        now = self.pool.clock()
        return {
            fp: self.pool.health(fp).status(now)
            for fp in (r.fingerprint for r in self.pool.records)
        }

    def _absorb_stream_failure(self, exc: AegisError, key: Any) -> None:
        from ..core.errors import ProviderAuthError, ProviderRateLimited

        if isinstance(exc, ProviderRateLimited):
            self.pool.report_rate_limited(
                key.fingerprint, retry_after=exc.context.get("retry_after")
            )
        elif isinstance(exc, ProviderAuthError):
            self.pool.report_auth_failure(key.fingerprint, exc.message)
        else:
            self.pool.report_failure(key.fingerprint)


def _selector_env() -> dict[str, str]:
    """The environment the pool discovers keys from (indirection for tests)."""
    import os

    return dict(os.environ)


def decision_summary(result: ShieldResult) -> dict[str, Any]:
    """Compact routing story for logs and the trace bus."""
    return {
        "model": result.model_id,
        "attempts": [
            {"model": r.model, "key": r.key_fingerprint, "outcome": r.outcome}
            for r in result.reports
        ],
    }
