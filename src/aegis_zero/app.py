"""Composition root: build a fully wired agent from Settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .core.config import Settings, load_settings
from .core.events import EventBus
from .core.models import Budget, Message
from .memory import Embedder, MemRLEngine, build_store
from .observability import Metrics, configure_logging, instrument
from .orchestrator import AgentEngine, AgentResult, ContextBuilder, EngineConfig
from .orchestrator.reliability import ReliabilityReport, reliability_report
from .providers import build_provider
from .providers.base import LLMProvider
from .tools import ApprovalGate, DenyAll, PolicyEngine, default_registry
from .tools.registry import ToolRegistry


@dataclass(slots=True)
class Aegis:
    """A fully assembled Aegis Zero agent."""

    engine: AgentEngine
    settings: Settings
    bus: EventBus
    metrics: Metrics
    provider: LLMProvider
    registry: ToolRegistry
    memory: MemRLEngine | None = None

    async def ask(
        self, goal: str, *, history: tuple[Message, ...] = (), budget: Budget | None = None
    ) -> AgentResult:
        return await self.engine.run(goal, history=history, budget=budget)

    async def reliability(
        self, goal: str, *, n: int = 5, k: int = 3, budget: Budget | None = None
    ) -> ReliabilityReport:
        """Run ``goal`` ``n`` times and report consistency (P4 / pass^k).

        Agents that pass pass@1 but fail pass^k are unreliable rather than
        incapable. This runs the goal repeatedly (bounded concurrency so a
        large ``n`` cannot exhaust the event loop) and aggregates the
        success rate, the pass^k streak probability, and the mean cost per
        run — the honest baseline for claiming any improvement.
        """
        import asyncio

        sem = asyncio.Semaphore(max(1, min(n, 8)))

        async def one() -> AgentResult:
            async with sem:
                return await self.engine.run(goal, budget=budget)

        results = await asyncio.gather(*(one() for _ in range(max(1, n))))
        return reliability_report(
            outcomes=[r.ok for r in results],
            k=k,
            tokens=[float(r.usage.total_tokens) for r in results],
            seconds=[r.elapsed_s for r in results],
            revisions=[float(r.revisions) for r in results],
        )

    async def aclose(self) -> None:
        self.bus.close()
        await self.provider.aclose()

    async def __aenter__(self) -> Aegis:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


def build_agent(
    settings: Settings | None = None,
    *,
    config_path: str | None = None,
    approval: ApprovalGate | None = None,
    registry: ToolRegistry | None = None,
    enable_memory: bool = True,
    enable_http_tool: bool = True,
) -> Aegis:
    """Wire providers, tools, policy, memory, and observability together."""
    settings = settings or load_settings(config_path)
    configure_logging(settings.log_level)

    provider = build_provider(
        settings.provider,
        settings.models.fallback_chain,
        primary_attempts=settings.models.primary_fallback_attempts,
    )
    tools = registry or default_registry(enable_http=enable_http_tool)

    policy = PolicyEngine(
        approval_threshold=settings.policy.approval_threshold,
        allow_network=settings.policy.allow_network,
        allowed_roots=settings.policy.allowed_roots,
        denied_tools=settings.policy.denied_tools,
    )

    memory: MemRLEngine | None = None
    if enable_memory:
        memory = MemRLEngine(
            build_store(settings.memory),
            Embedder(provider, model=settings.models.embed),
        )

    bus = EventBus()
    metrics = instrument(
        bus, trace_path=settings.trace_dir + "/trace.jsonl" if settings.trace_dir else None
    )

    engine = AgentEngine(
        provider,
        registry=tools,
        policy=policy,
        approval=approval or DenyAll(),
        memory=memory,
        context=ContextBuilder(
            memory,
            memory_limit=settings.memory.top_k,
            harness_path=_harness_path(settings),
            prompt_budget_for=settings.models.prompt_budget,
        ),
        bus=bus,
        config=EngineConfig(
            fast_model=settings.models.fast,
            deep_model=settings.models.deep,
            budget=Budget(
                max_steps=settings.max_steps,
                max_tokens=settings.max_tokens,
                max_seconds=settings.max_seconds,
            ),
        ),
        harness_path=_harness_path(settings),
    )

    return Aegis(
        engine=engine,
        settings=settings,
        bus=bus,
        metrics=metrics,
        provider=provider,
        registry=tools,
        memory=memory,
    )


def _harness_path(settings: Settings) -> str | None:
    path = settings.harness_path.strip()
    return path or None
