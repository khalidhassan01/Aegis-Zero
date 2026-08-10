"""The Aegis Zero agent engine.

Execution model
---------------
1. Plan     - decompose the goal (skipped for trivial goals).
2. Execute  - run subtasks, in parallel when independent. Each subtask runs
              a bounded tool-calling loop.
3. Critique - an adversarial auditor reviews the synthesis.
4. Revise   - at most ``max_revisions`` corrective passes.
5. Learn    - reward the memories that contributed to a good outcome.

Everything is async, cancellable, budget-bounded, and emits events.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import (
    AegisError,
    ApprovalDenied,
    BudgetExceeded,
    Cancelled,
    PolicyDenied,
)
from ..core.events import Event, EventBus, EventType, NullBus
from ..core.models import (
    Budget,
    Complexity,
    Decision,
    Message,
    RunState,
    ToolCall,
    ToolResult,
    Usage,
)
from ..memory.memrl import MemRLEngine, signal_from_outcome
from ..providers.base import LLMProvider
from ..tools.approval import ApprovalGate, ApprovalRequest, DenyAll
from ..tools.policy import PolicyEngine, redact
from ..tools.registry import ToolRegistry
from .agents import (
    FORGE_SYSTEM,
    Critique,
    Plan,
    Subtask,
    auditor_prompt,
    heuristic_complexity,
    parse_critique,
    parse_plan,
    planner_prompt,
    scout_prompt,
)
from .context import ContextBuilder

SYNTHESIS_SYSTEM = """You are the Synthesizer in Aegis Zero. Merge the
subtask results into one coherent answer for the user. Resolve conflicts
explicitly, drop redundancy, and never invent facts absent from the inputs."""


@dataclass(slots=True)
class AgentResult:
    run_id: str
    goal: str
    answer: str
    ok: bool = True
    critique: Critique | None = None
    plan: Plan | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    steps: int = 0
    revisions: int = 0
    elapsed_s: float = 0.0
    error: str | None = None
    memory_ids: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return self.critique.confidence if self.critique else 0.0

    def summary(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "ok": self.ok, "steps": self.steps,
                "revisions": self.revisions, "tokens": self.usage.total_tokens,
                "tool_calls": len(self.tool_results),
                "confidence": round(self.confidence, 3),
                "elapsed_s": round(self.elapsed_s, 2)}


@dataclass(slots=True)
class EngineConfig:
    fast_model: str = "qwen2.5:7b"
    deep_model: str = "qwen2.5:7b"
    budget: Budget = field(default_factory=Budget)
    max_revisions: int = 1
    max_tool_iterations: int = 8
    max_parallel: int = 4
    enable_planning: bool = True
    enable_scout: bool = True
    enable_critique: bool = True
    enable_memory_write: bool = True
    min_confidence: float = 0.6
    temperature: float = 0.2


class AgentEngine:
    """Orchestrates providers, tools, policy, and memory into a run."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        registry: ToolRegistry | None = None,
        policy: PolicyEngine | None = None,
        approval: ApprovalGate | None = None,
        memory: MemRLEngine | None = None,
        context: ContextBuilder | None = None,
        bus: EventBus | None = None,
        config: EngineConfig | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.policy = policy or PolicyEngine()
        self.approval = approval or DenyAll()
        self.memory = memory
        self.context = context or ContextBuilder(memory)
        self.bus = bus or NullBus()
        self.cfg = config or EngineConfig()

    # -- public API --------------------------------------------------

    async def run(self, goal: str, *, history: Sequence[Message] = (),
                  budget: Budget | None = None) -> AgentResult:
        state = RunState(goal=goal)
        budget = budget or self.cfg.budget
        result = AgentResult(run_id=state.run_id, goal=goal, answer="")

        await self._emit(EventType.RUN_START, state, {"goal": goal[:400]})
        try:
            result = await self._execute(goal, history, state, budget, result)
        except Cancelled as exc:
            result.ok, result.error = False, str(exc)
        except (PolicyDenied, ApprovalDenied) as exc:
            result.ok, result.error = False, str(exc)
            result.answer = f"Blocked by policy: {exc}"
        except BudgetExceeded as exc:
            result.ok, result.error = False, str(exc)
            if not result.answer:
                result.answer = "Run halted: budget exhausted before completion."
        except AegisError as exc:
            result.ok, result.error = False, str(exc)
            await self._emit(EventType.RUN_ERROR, state, {"error": str(exc)})
        finally:
            result.usage = state.usage
            result.steps = state.steps
            result.elapsed_s = state.elapsed
            await self._emit(EventType.RUN_END, state, result.summary())

        return result

    def cancel(self, state: RunState) -> None:
        state.cancelled = True

    # -- pipeline ----------------------------------------------------

    async def _execute(self, goal: str, history: Sequence[Message],
                       state: RunState, budget: Budget,
                       result: AgentResult) -> AgentResult:
        plan = await self._plan(goal, state, budget)
        result.plan = plan

        recon = ""
        if self.cfg.enable_scout and plan.complexity in (Complexity.MODERATE,
                                                         Complexity.COMPLEX):
            recon = await self._scout(goal, state, budget)

        outputs = await self._run_subtasks(plan, recon, history, state, budget, result)
        answer = await self._synthesize(goal, plan, outputs, state, budget)

        if self.cfg.enable_critique:
            answer, critique, revisions = await self._critique_loop(
                goal, answer, recon, state, budget
            )
            result.critique, result.revisions = critique, revisions

        result.answer = answer
        result.ok = result.critique is None or result.critique.verdict != "fail"
        await self._learn(goal, answer, result)
        return result

    async def _plan(self, goal: str, state: RunState, budget: Budget) -> Plan:
        cheap = heuristic_complexity(goal)
        if not self.cfg.enable_planning or cheap in (Complexity.TRIVIAL,
                                                     Complexity.SIMPLE):
            return Plan(cheap, False, (Subtask("s1", goal),))
        completion = await self._call(planner_prompt(goal), state, budget,
                                      model=self.cfg.fast_model, step="plan")
        return parse_plan(completion, goal)

    async def _scout(self, goal: str, state: RunState, budget: Budget) -> str:
        completion = await self._call(scout_prompt(goal), state, budget,
                                      model=self.cfg.fast_model, step="scout")
        return completion.text

    async def _run_subtasks(self, plan: Plan, recon: str,
                            history: Sequence[Message], state: RunState,
                            budget: Budget, result: AgentResult) -> list[str]:
        waves = _topological_waves(plan.subtasks)
        outputs: dict[str, str] = {}
        sem = asyncio.Semaphore(self.cfg.max_parallel)

        async def one(task: Subtask) -> tuple[str, str]:
            async with sem:
                upstream = "\n\n".join(
                    f"[{dep} result]\n{outputs[dep]}"
                    for dep in task.depends_on if dep in outputs
                )
                text = await self._forge(task, recon, upstream, history,
                                         state, budget, result)
                return task.id, text

        for wave in waves:
            self._check(state, budget)
            if len(wave) == 1 or not plan.parallel:
                for task in wave:
                    tid, text = await one(task)
                    outputs[tid] = text
            else:
                for tid, text in await asyncio.gather(*(one(t) for t in wave)):
                    outputs[tid] = text

        return [outputs[t.id] for t in plan.subtasks if t.id in outputs]

    async def _forge(self, task: Subtask, recon: str, upstream: str,
                     history: Sequence[Message], state: RunState,
                     budget: Budget, result: AgentResult) -> str:
        extra: dict[str, Any] = {}
        if recon:
            extra["reconnaissance"] = recon[:2000]
        if upstream:
            extra["upstream results"] = upstream[:4000]

        packet = await self.context.build(task.goal, history,
                                          system=FORGE_SYSTEM, extra=extra)
        messages = [*packet.to_messages(), Message(role="user", content=task.goal)]
        result.memory_ids.extend(packet.memory_ids)

        schemas = self.registry.schemas() or None
        for _ in range(self.cfg.max_tool_iterations):
            self._check(state, budget)
            completion = await self._call(messages, state, budget,
                                          model=self.cfg.deep_model,
                                          step=f"forge:{task.id}", tools=schemas)
            if not completion.tool_calls:
                return completion.text

            messages.append(Message(role="assistant", content=completion.text,
                                    tool_calls=completion.tool_calls))
            results = await self._invoke_tools(completion.tool_calls, state, budget)
            result.tool_results.extend(results)
            messages.extend(r.as_message() for r in results)

        # Tool budget exhausted: ask for a final answer with no tools.
        messages.append(Message(role="user",
                                content="Tool budget reached. Give your best final "
                                        "answer now using what you have."))
        final = await self._call(messages, state, budget,
                                 model=self.cfg.deep_model,
                                 step=f"forge:{task.id}:final")
        return final.text

    async def _invoke_tools(self, calls: Sequence[ToolCall], state: RunState,
                            budget: Budget) -> list[ToolResult]:
        async def run_one(call: ToolCall) -> ToolResult:
            state.tool_calls += 1
            if state.tool_calls > budget.max_tool_calls:
                return ToolResult(tool=call.name, ok=False, call_id=call.id,
                                  error="tool-call budget exhausted")

            verdict = self.policy.decide(call.name, call.arguments)
            await self._emit(EventType.POLICY_DECISION, state, {
                "tool": call.name, "decision": verdict.decision.value,
                "risk": verdict.risk.value, "reason": verdict.reason,
            })

            if verdict.decision is Decision.DENY:
                return ToolResult(tool=call.name, ok=False, call_id=call.id,
                                  decision=Decision.DENY,
                                  error=f"policy denied: {verdict.reason}")

            if verdict.decision is Decision.APPROVE:
                req = ApprovalRequest(state.run_id, call.name, verdict.risk,
                                      verdict.reason, verdict.arguments)
                await self._emit(EventType.APPROVAL_REQUEST, state,
                                 {"tool": call.name, "risk": verdict.risk.value})
                granted = await self.approval.request(req)
                await self._emit(EventType.APPROVAL_RESULT, state,
                                 {"tool": call.name, "granted": granted})
                if not granted:
                    return ToolResult(tool=call.name, ok=False, call_id=call.id,
                                      decision=Decision.DENY,
                                      error="human approval denied")

            args = verdict.arguments if verdict.decision is Decision.SANITIZE \
                else call.arguments
            await self._emit(EventType.TOOL_START, state, {"tool": call.name})
            out = await self.registry.execute(call.name, args, call_id=call.id)
            await self._emit(EventType.TOOL_END, state, {
                "tool": call.name, "ok": out.ok,
                "duration_ms": round(out.duration_ms, 1),
                "error": redact(out.error) if out.error else None,
            })
            return out

        return list(await asyncio.gather(*(run_one(c) for c in calls)))

    async def _synthesize(self, goal: str, plan: Plan, outputs: Sequence[str],
                          state: RunState, budget: Budget) -> str:
        if not outputs:
            return "No subtask produced a result."
        if len(outputs) == 1:
            return outputs[0]
        joined = "\n\n".join(f"### Result {i + 1}\n{o}"
                              for i, o in enumerate(outputs))
        completion = await self._call([
            Message(role="system", content=SYNTHESIS_SYSTEM),
            Message(role="user", content=f"GOAL:\n{goal}\n\nRESULTS:\n{joined}"),
        ], state, budget, model=self.cfg.deep_model, step="synthesize")
        return completion.text

    async def _critique_loop(self, goal: str, answer: str, recon: str,
                             state: RunState,
                             budget: Budget) -> tuple[str, Critique, int]:
        critique = parse_critique(
            await self._call(auditor_prompt(goal, answer), state, budget,
                             model=self.cfg.fast_model, step="audit")
        )
        revisions = 0
        while (revisions < self.cfg.max_revisions
               and not critique.passed
               and critique.verdict != "fail"):
            revisions += 1
            issues = "\n".join(f"- {i}" for i in critique.issues) or "- (unspecified)"
            completion = await self._call([
                Message(role="system", content=FORGE_SYSTEM),
                Message(role="user", content=(
                    f"GOAL:\n{goal}\n\nPREVIOUS ANSWER:\n{answer}\n\n"
                    f"AUDITOR ISSUES:\n{issues}\n\n"
                    f"SUGGESTION: {critique.suggestion}\n\n"
                    "Produce a corrected, complete answer."
                )),
            ], state, budget, model=self.cfg.deep_model, step=f"revise:{revisions}")
            answer = completion.text
            critique = parse_critique(
                await self._call(auditor_prompt(goal, answer), state, budget,
                                 model=self.cfg.fast_model,
                                 step=f"audit:{revisions}")
            )
        return answer, critique, revisions

    async def _learn(self, goal: str, answer: str, result: AgentResult) -> None:
        if self.memory is None:
            return
        confidence = result.confidence or 0.5
        if result.memory_ids:
            signal = signal_from_outcome(success=result.ok, confidence=confidence)
            with contextlib.suppress(Exception):
                await self.memory.reward_many(
                    list(dict.fromkeys(result.memory_ids)), signal
                )
        if self.cfg.enable_memory_write and result.ok and confidence >= self.cfg.min_confidence:
            with contextlib.suppress(Exception):
                await self.memory.remember(
                    f"Q: {goal}\nA: {answer[:1500]}",
                    kind="episode",
                    metadata={"run_id": result.run_id, "confidence": confidence},
                )

    # -- primitives --------------------------------------------------

    async def _call(self, messages: Sequence[Message], state: RunState,
                    budget: Budget, *, model: str, step: str,
                    tools: list[dict[str, Any]] | None = None):
        self._check(state, budget)
        state.steps += 1
        await self._emit(EventType.LLM_START, state, {"step": step, "model": model})
        started = time.perf_counter()
        completion = await self.provider.complete(
            messages, model=model, tools=tools, temperature=self.cfg.temperature
        )
        state.usage = state.usage + completion.usage
        await self._emit(EventType.LLM_END, state, {
            "step": step, "model": completion.model,
            "tokens": completion.usage.total_tokens,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "tool_calls": len(completion.tool_calls),
        })
        return completion

    def _check(self, state: RunState, budget: Budget) -> None:
        if state.cancelled:
            raise Cancelled("run cancelled", context={"run_id": state.run_id})
        if state.steps >= budget.max_steps:
            raise BudgetExceeded("step budget exhausted",
                                 context={"steps": state.steps})
        if state.usage.total_tokens >= budget.max_tokens:
            raise BudgetExceeded("token budget exhausted",
                                 context={"tokens": state.usage.total_tokens})
        if state.elapsed >= budget.max_seconds:
            raise BudgetExceeded("time budget exhausted",
                                 context={"elapsed": round(state.elapsed, 1)})

    async def _emit(self, kind: EventType, state: RunState,
                    data: dict[str, Any]) -> None:
        await self.bus.publish(Event(type=kind, run_id=state.run_id, data=data))


def _topological_waves(subtasks: Sequence[Subtask]) -> list[list[Subtask]]:
    """Group subtasks into dependency waves; each wave runs in parallel."""
    pending = {t.id: t for t in subtasks}
    done: set[str] = set()
    waves: list[list[Subtask]] = []

    while pending:
        wave = [t for t in pending.values()
                if all(d in done or d not in pending for d in t.depends_on)]
        if not wave:  # dependency cycle: run the remainder sequentially
            wave = [next(iter(pending.values()))]
        waves.append(wave)
        for t in wave:
            pending.pop(t.id, None)
            done.add(t.id)
    return waves
