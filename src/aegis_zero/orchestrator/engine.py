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
from dataclasses import dataclass, field, replace
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
from .citations import citation_summary, grounded_ids, parse_citations
from .context import ContextBuilder, ContextPacket
from .verifier import Verification, run_default_checks

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
    #: Recalled memories a verifier hard-failure later proved fed a wrong
    #: claim. They are tombstoned (P6.5) and must NOT receive the success
    #: reward below -- rewarding a memory that the verifier just invalidated
    #: would be self-contradictory credit assignment (P6).
    invalidated_memory_ids: set[str] = field(default_factory=set)
    #: Memories a Forge step *declared* it used via the citation protocol
    #: (P6, cite-level attribution): the ``MEMORIES USED: m1, …`` line.
    cited_memory_ids: list[str] = field(default_factory=list)
    #: Memories whose rendered text reappeared verbatim in a Forge reply
    #: (grounded reuse) even though the model did not declare them.
    grounded_memory_ids: set[str] = field(default_factory=set)
    #: Whether every Forge step that had memories in context emitted the
    #: citation line. ``None`` when nothing was recalled at all.
    citation_protocol_followed: bool | None = None

    @property
    def confidence(self) -> float:
        return self.critique.confidence if self.critique else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "ok": self.ok,
            "steps": self.steps,
            "revisions": self.revisions,
            "tokens": self.usage.total_tokens,
            "tool_calls": len(self.tool_results),
            "confidence": round(self.confidence, 3),
            "elapsed_s": round(self.elapsed_s, 2),
            "memories_recalled": len(set(self.memory_ids)),
            "memories_credited": len(set(self.cited_memory_ids) | self.grounded_memory_ids),
            "citation_protocol": self.citation_protocol_followed,
        }


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
    #: Attempt a corrective pass when the auditor returns "fail".
    #: Set False to treat "fail" as terminal and stop immediately.
    revise_on_fail: bool = True
    #: A "fail" verdict gets at most this many attempts, regardless of
    #: ``max_revisions``, so one harsh verdict cannot exhaust the budget.
    max_fail_revisions: int = 1
    #: Cite-level attribution (P6). When True (default), only memories a
    #: Forge step declared (citation line) or demonstrably reused (verbatim
    #: span) receive reward weight. When False, the legacy coarse reward
    #: (every surviving recalled memory equally) applies -- kept as an
    #: ablation switch so the two policies can be A/B measured.
    citation_protocol: bool = True


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
        harness_path: str | None = None,
    ) -> None:
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.policy = policy or PolicyEngine()
        self.approval = approval or DenyAll()
        self.memory = memory
        self.context = context or ContextBuilder(memory, harness_path=harness_path)
        self.bus = bus or NullBus()
        self.cfg = config or EngineConfig()
        self.harness_path = harness_path

    # -- public API --------------------------------------------------

    async def run(
        self, goal: str, *, history: Sequence[Message] = (), budget: Budget | None = None
    ) -> AgentResult:
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

    async def _execute(
        self,
        goal: str,
        history: Sequence[Message],
        state: RunState,
        budget: Budget,
        result: AgentResult,
    ) -> AgentResult:
        plan = await self._plan(goal, state, budget)
        result.plan = plan

        recon = ""
        if self.cfg.enable_scout and plan.complexity in (
            Complexity.MODERATE,
            Complexity.COMPLEX,
        ):
            recon = await self._scout(goal, state, budget)

        outputs = await self._run_subtasks(plan, recon, history, state, budget, result)
        answer = await self._synthesize(goal, plan, outputs, state, budget)

        verification: Verification | None = None
        if self.cfg.enable_critique:
            answer, critique, revisions, verification = await self._critique_loop(
                goal, answer, recon, state, budget
            )
            result.critique, result.revisions = critique, revisions
            # P6.5: a hard factual check failure means a recalled memory likely
            # fed a wrong claim. Tombstone the memories that were in context so
            # they stop ranking highly, rather than poisoning future runs.
            if verification.hard_failures and self.memory and result.memory_ids:
                await self.memory.invalidate_by_ids(result.memory_ids, reason="failed verifier")
                # The run produced a verifier-proven wrong answer, so the
                # recalled memories did not help. Exclude every recalled id
                # from the success reward below -- rewarding a memory the
                # verifier just tombstoned would be self-contradictory credit
                # assignment (P6).
                result.invalidated_memory_ids.update(result.memory_ids)

        result.answer = answer
        result.ok = result.critique is None or result.critique.verdict != "fail"
        await self._learn(goal, answer, result, verification)
        return result

    async def _plan(self, goal: str, state: RunState, budget: Budget) -> Plan:
        cheap = heuristic_complexity(goal)
        if not self.cfg.enable_planning or cheap in (Complexity.TRIVIAL, Complexity.SIMPLE):
            return Plan(cheap, False, (Subtask("s1", goal),))
        completion = await self._call(
            planner_prompt(goal), state, budget, model=self.cfg.fast_model, step="plan"
        )
        return parse_plan(completion, goal)

    async def _scout(self, goal: str, state: RunState, budget: Budget) -> str:
        completion = await self._call(
            scout_prompt(goal), state, budget, model=self.cfg.fast_model, step="scout"
        )
        return completion.text

    async def _run_subtasks(
        self,
        plan: Plan,
        recon: str,
        history: Sequence[Message],
        state: RunState,
        budget: Budget,
        result: AgentResult,
    ) -> list[str]:
        waves = _topological_waves(plan.subtasks)
        outputs: dict[str, str] = {}
        sem = asyncio.Semaphore(self.cfg.max_parallel)

        async def one(task: Subtask) -> tuple[str, str]:
            async with sem:
                upstream = "\n\n".join(
                    f"[{dep} result]\n{outputs[dep]}"
                    for dep in task.depends_on
                    if dep in outputs
                )
                text = await self._forge(task, recon, upstream, history, state, budget, result)
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

    async def _forge(
        self,
        task: Subtask,
        recon: str,
        upstream: str,
        history: Sequence[Message],
        state: RunState,
        budget: Budget,
        result: AgentResult,
    ) -> str:
        extra: dict[str, Any] = {}
        if recon:
            extra["reconnaissance"] = recon[:2000]
        if upstream:
            extra["upstream results"] = upstream[:4000]

        packet = await self.context.build(
            task.goal, history, system=FORGE_SYSTEM, extra=extra, model=self.cfg.deep_model
        )
        messages = [*packet.to_messages(), Message(role="user", content=task.goal)]
        result.memory_ids.extend(packet.memory_ids)

        schemas = self.registry.schemas() or None
        for _ in range(self.cfg.max_tool_iterations):
            self._check(state, budget)
            completion = await self._call(
                messages,
                state,
                budget,
                model=self.cfg.deep_model,
                step=f"forge:{task.id}",
                tools=schemas,
            )
            if not completion.tool_calls:
                return self._attribute_citations(completion.text, packet, result)

            messages.append(
                Message(
                    role="assistant", content=completion.text, tool_calls=completion.tool_calls
                )
            )
            results = await self._invoke_tools(completion.tool_calls, state, budget)
            result.tool_results.extend(results)
            messages.extend(r.as_message() for r in results)

        # Tool budget exhausted: ask for a final answer with no tools.
        messages.append(
            Message(
                role="user",
                content="Tool budget reached. Give your best final "
                "answer now using what you have.",
            )
        )
        final = await self._call(
            messages, state, budget, model=self.cfg.deep_model, step=f"forge:{task.id}:final"
        )
        return self._attribute_citations(final.text, packet, result)

    def _attribute_citations(
        self, text: str, packet: ContextPacket, result: AgentResult
    ) -> str:
        """Apply the memory citation protocol to one Forge reply (P6).

        Strips the ``MEMORIES USED`` line so it never reaches the
        synthesizer, the verifier, or the user; records declared citations
        and grounded reuse on the result; returns the clean text. Steps with
        no memories in context are vacuous and change nothing.
        """
        if not self.cfg.citation_protocol or not packet.memory_tags:
            return text
        report = parse_citations(text, packet.memory_tags)
        result.cited_memory_ids.extend(report.cited_ids)
        result.grounded_memory_ids.update(grounded_ids(report.clean_text, packet.memories))
        if result.citation_protocol_followed is None:
            result.citation_protocol_followed = report.followed
        else:
            result.citation_protocol_followed = result.citation_protocol_followed and (
                report.followed
            )
        return report.clean_text

    async def _invoke_tools(
        self, calls: Sequence[ToolCall], state: RunState, budget: Budget
    ) -> list[ToolResult]:
        async def run_one(call: ToolCall) -> ToolResult:
            state.tool_calls += 1
            if state.tool_calls > budget.max_tool_calls:
                return ToolResult(
                    tool=call.name,
                    ok=False,
                    call_id=call.id,
                    error="tool-call budget exhausted",
                )

            verdict = self.policy.decide(call.name, call.arguments)
            await self._emit(
                EventType.POLICY_DECISION,
                state,
                {
                    "tool": call.name,
                    "decision": verdict.decision.value,
                    "risk": verdict.risk.value,
                    "reason": verdict.reason,
                },
            )

            if verdict.decision is Decision.DENY:
                return ToolResult(
                    tool=call.name,
                    ok=False,
                    call_id=call.id,
                    decision=Decision.DENY,
                    error=f"policy denied: {verdict.reason}",
                )

            if verdict.decision is Decision.APPROVE:
                req = ApprovalRequest(
                    state.run_id, call.name, verdict.risk, verdict.reason, verdict.arguments
                )
                await self._emit(
                    EventType.APPROVAL_REQUEST,
                    state,
                    {"tool": call.name, "risk": verdict.risk.value},
                )
                granted = await self.approval.request(req)
                await self._emit(
                    EventType.APPROVAL_RESULT, state, {"tool": call.name, "granted": granted}
                )
                if not granted:
                    return ToolResult(
                        tool=call.name,
                        ok=False,
                        call_id=call.id,
                        decision=Decision.DENY,
                        error="human approval denied",
                    )

            args = (
                verdict.arguments if verdict.decision is Decision.SANITIZE else call.arguments
            )
            await self._emit(EventType.TOOL_START, state, {"tool": call.name})
            out = await self.registry.execute(call.name, args, call_id=call.id)
            state.tool_outputs.append(out)
            await self._emit(
                EventType.TOOL_END,
                state,
                {
                    "tool": call.name,
                    "ok": out.ok,
                    "duration_ms": round(out.duration_ms, 1),
                    "error": redact(out.error) if out.error else None,
                },
            )
            return out

        return list(await asyncio.gather(*(run_one(c) for c in calls)))

    async def _synthesize(
        self, goal: str, plan: Plan, outputs: Sequence[str], state: RunState, budget: Budget
    ) -> str:
        if not outputs:
            return "No subtask produced a result."
        if len(outputs) == 1:
            return outputs[0]
        joined = "\n\n".join(f"### Result {i + 1}\n{o}" for i, o in enumerate(outputs))
        completion = await self._call(
            [
                Message(role="system", content=SYNTHESIS_SYSTEM),
                Message(role="user", content=f"GOAL:\n{goal}\n\nRESULTS:\n{joined}"),
            ],
            state,
            budget,
            model=self.cfg.deep_model,
            step="synthesize",
        )
        return completion.text

    async def _critique_loop(
        self, goal: str, answer: str, recon: str, state: RunState, budget: Budget
    ) -> tuple[str, Critique, int, Verification]:
        # Deterministic verification runs BEFORE the LLM auditor. A hard
        # check failure (e.g. a wrong arithmetic total) forces a revision
        # regardless of what the model says about its own answer -- this is
        # the external signal intrinsic self-correction lacks
        # (Huang et al., ICLR 2024).
        verification = run_default_checks(goal, answer, list(state.tool_outputs))
        forced = bool(verification.hard_failures)

        critique = parse_critique(
            await self._call(
                auditor_prompt(goal, answer),
                state,
                budget,
                model=self.cfg.fast_model,
                step="audit",
            )
        )
        if forced and critique.verdict == "pass":
            # The model is overconfident; downgrade so the revision loop runs.
            critique = Critique(
                "revise",
                min(critique.confidence, 0.4),
                tuple(v.detail for v in verification.hard_failures),
                verification.report,
            )
        revisions = 0
        # A "fail" verdict previously skipped revision entirely, so the worst
        # answers were the only ones never corrected. That is defensible if
        # "fail" means unsalvageable, but with small auditor models it mostly
        # wasted the run. It is now an explicit policy, and a fail is given at
        # most one corrective attempt so a harsh verdict cannot burn the whole
        # revision budget.
        while revisions < self._revision_cap(critique) and not critique.passed:
            revisions += 1
            issues = "\n".join(f"- {i}" for i in critique.issues) or "- (unspecified)"
            completion = await self._call(
                [
                    Message(role="system", content=FORGE_SYSTEM),
                    Message(
                        role="user",
                        content=(
                            f"GOAL:\n{goal}\n\nPREVIOUS ANSWER:\n{answer}\n\n"
                            f"AUDITOR ISSUES:\n{issues}\n\n"
                            f"SUGGESTION: {critique.suggestion}\n\n"
                            "Produce a corrected, complete answer."
                        ),
                    ),
                ],
                state,
                budget,
                model=self.cfg.deep_model,
                step=f"revise:{revisions}",
            )
            answer = completion.text
            critique = parse_critique(
                await self._call(
                    auditor_prompt(goal, answer),
                    state,
                    budget,
                    model=self.cfg.fast_model,
                    step=f"audit:{revisions}",
                )
            )
        return answer, critique, revisions, verification

    def _revision_cap(self, critique: Critique) -> int:
        """How many revisions this verdict is allowed to trigger."""
        if critique.verdict == "fail":
            if not self.cfg.revise_on_fail:
                return 0
            return min(self.cfg.max_fail_revisions, self.cfg.max_revisions)
        return self.cfg.max_revisions

    @staticmethod
    def _memory_credits(result: AgentResult, signal: float) -> dict[str, float]:
        """Per-memory reward weights for one run (P6 cite-level).

        A declared citation earns the full signal. A grounded reuse the
        model did not declare earns half: the verbatim span proves the
        memory influenced the reply, which is weaker evidence than the model
        saying so explicitly. Recalled-but-unevidenced memories earn
        nothing -- absence of use is not evidence of harm, so they are not
        punished either. Verifier-invalidated memories are excluded from
        both channels.
        """
        credited: dict[str, float] = {}
        for mid in result.cited_memory_ids:
            if mid not in result.invalidated_memory_ids:
                credited[mid] = signal
        for mid in sorted(result.grounded_memory_ids):
            if mid in result.invalidated_memory_ids or mid in credited:
                continue
            credited[mid] = 0.5 * signal
        return credited

    async def _learn(
        self, goal: str, answer: str, result: AgentResult, verification: Any = None
    ) -> None:
        if self.memory is None:
            return
        confidence = result.confidence or 0.5
        if result.memory_ids:
            signal = signal_from_outcome(success=result.ok, confidence=confidence)
            if self.cfg.citation_protocol:
                # P6 -- cite-level credit assignment. Only memories a Forge
                # step declared (citation line) or demonstrably reused
                # (verbatim span in the reply) receive reward weight; the
                # rest were recalled but never evidenced, so they earn
                # nothing this run -- not punished, just not credited.
                # Verifier-invalidated memories are excluded from both
                # channels: rewarding them would contradict the tombstone.
                credited = self._memory_credits(result, signal)
                applied = 0
                if credited:
                    with contextlib.suppress(Exception):
                        applied = await self.memory.reward_attributed(credited.items())
                # Emit even when nothing earned credit: "recalled, none
                # evidenced" is exactly the data the P6 fine-grained-
                # attribution metric needs, and ``applied`` reports how many
                # rewards actually landed (0 if the store failed).
                with contextlib.suppress(Exception):
                    await self.bus.publish(
                        Event(
                            type=EventType.MEMORY_CREDIT,
                            run_id=result.run_id,
                            data={
                                "signal": round(signal, 3),
                                "applied": applied,
                                **citation_summary(
                                    result.memory_ids,
                                    result.cited_memory_ids,
                                    result.grounded_memory_ids,
                                    result.citation_protocol_followed,
                                ),
                            },
                        )
                    )
            else:
                # Ablation switch: the legacy coarse reward (every surviving
                # recalled memory, equally) so the two policies can be
                # A/B-measured honestly rather than asserted.
                rewarded = [
                    mid
                    for mid in dict.fromkeys(result.memory_ids)
                    if mid not in result.invalidated_memory_ids
                ]
                if rewarded:
                    with contextlib.suppress(Exception):
                        await self.memory.reward_many(rewarded, signal)
        if self.cfg.enable_memory_write and result.ok and confidence >= self.cfg.min_confidence:
            with contextlib.suppress(Exception):
                await self.memory.remember(
                    f"Q: {goal}\nA: {answer[:1500]}",
                    kind="episode",
                    metadata={"run_id": result.run_id, "confidence": confidence},
                )

        # Continual Harness: persist a GROUNDED lesson from the verified
        # outcome. Unlike prime-agent's self-narrative /refine, the decision
        # is driven by the deterministic verifier + task success, so a lesson
        # is only stored when the run was actually correct. Scope is global
        # because a verified lesson is by definition reusable.
        if self.context.harness_path:
            with contextlib.suppress(Exception):
                from ..memory.harness import HarnessController
                from ..memory.harness_extraction import propose_from_outcome
                from .verifier import Verification

                v = verification if isinstance(verification, Verification) else None
                # When critique is disabled there is no auditor confidence;
                # treat an otherwise-successful run as implicitly verified.
                eff_confidence = confidence if v is not None else max(confidence, 1.0)
                proposal = propose_from_outcome(
                    goal=goal,
                    answer=answer,
                    verification=v or Verification(checks=[]),
                    run_ok=result.ok,
                    confidence=eff_confidence,
                )
                if proposal.edits:
                    HarnessController(self.context.harness_path).apply(proposal, scope="global")

    # -- primitives --------------------------------------------------

    async def _call(
        self,
        messages: Sequence[Message],
        state: RunState,
        budget: Budget,
        *,
        model: str,
        step: str,
        tools: list[dict[str, Any]] | None = None,
    ):
        self._check(state, budget)
        state.steps += 1
        await self._emit(EventType.LLM_START, state, {"step": step, "model": model})
        started = time.perf_counter()
        completion = await self.provider.complete(
            messages, model=model, tools=tools, temperature=self.cfg.temperature
        )
        state.usage = state.usage + completion.usage
        await self._emit(
            EventType.LLM_END,
            state,
            {
                "step": step,
                "model": completion.model,
                "tokens": completion.usage.total_tokens,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "tool_calls": len(completion.tool_calls),
            },
        )
        return completion

    def _check(self, state: RunState, budget: Budget) -> None:
        if state.cancelled:
            raise Cancelled("run cancelled", context={"run_id": state.run_id})
        if state.steps >= budget.max_steps:
            raise BudgetExceeded("step budget exhausted", context={"steps": state.steps})
        if state.usage.total_tokens >= budget.max_tokens:
            raise BudgetExceeded(
                "token budget exhausted", context={"tokens": state.usage.total_tokens}
            )
        if state.elapsed >= budget.max_seconds:
            raise BudgetExceeded(
                "time budget exhausted", context={"elapsed": round(state.elapsed, 1)}
            )

    async def _emit(self, kind: EventType, state: RunState, data: dict[str, Any]) -> None:
        await self.bus.publish(Event(type=kind, run_id=state.run_id, data=data))


def normalize_subtasks(subtasks: Sequence[Subtask]) -> list[Subtask]:
    """Repair a plan the model may have emitted badly.

    An LLM planner will occasionally produce duplicate ids, self-references,
    or dependencies on tasks that do not exist. Keying a dict on the raw ids
    silently dropped whole subtasks, so the repairs are explicit here.
    """
    seen: dict[str, int] = {}
    fixed: list[Subtask] = []
    for i, task in enumerate(subtasks):
        tid = task.id or f"s{i + 1}"
        if tid in seen:  # duplicate id: suffix it rather than lose the task
            seen[tid] += 1
            tid = f"{tid}__{seen[tid]}"
        else:
            seen[tid] = 0
        fixed.append(replace(task, id=tid))

    valid = {t.id for t in fixed}
    out: list[Subtask] = []
    for task in fixed:
        deps = tuple(d for d in dict.fromkeys(task.depends_on) if d in valid and d != task.id)
        out.append(replace(task, depends_on=deps) if deps != task.depends_on else task)
    return out


def _topological_waves(subtasks: Sequence[Subtask]) -> list[list[Subtask]]:
    """Group subtasks into dependency waves; each wave runs in parallel.

    Input is normalized first, so ids are unique and every dependency refers
    to a real task. A genuine cycle is broken deterministically by running
    the lowest-id member of the cycle first.
    """
    tasks = normalize_subtasks(subtasks)
    pending = {t.id: t for t in tasks}
    done: set[str] = set()
    waves: list[list[Subtask]] = []

    while pending:
        wave = [t for t in pending.values() if all(d in done for d in t.depends_on)]
        if not wave:
            # Cycle. Break it deterministically instead of by dict order.
            stuck = min(pending.values(), key=lambda t: t.id)
            wave = [stuck]
        waves.append(wave)
        for t in wave:
            pending.pop(t.id, None)
            done.add(t.id)
    return waves
