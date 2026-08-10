"""Command-line interface for Aegis Zero."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, replace
from typing import Any

from . import __version__
from .app import build_agent
from .core.config import load_settings
from .core.errors import AegisError
from .core.events import EventType
from .core.models import Budget
from .memory.harness import HarnessController, HarnessEntry, load_harness_state
from .tools.approval import AutoApprove, ConsoleGate, DenyAll


def _gate(name: str) -> Any:
    return {"console": ConsoleGate(), "auto": AutoApprove(), "deny": DenyAll()}[name]


async def cmd_run(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    if args.model:
        settings = settings.with_overrides(
            models=replace(settings.models, fast=args.model, deep=args.model)
        )
    agent = build_agent(
        settings, approval=_gate(args.approve), enable_memory=not args.no_memory
    )

    if args.verbose:
        agent.bus.subscribe(
            lambda e: (
                print(f"  · {e.type.value} {e.data}", file=sys.stderr)
                if e.type in (EventType.TOOL_END, EventType.POLICY_DECISION, EventType.LLM_END)
                else None
            )
        )

    async with agent:
        result = await agent.ask(
            args.goal,
            budget=Budget(max_steps=args.max_steps, max_seconds=args.timeout),
        )
        if args.json:
            print(
                json.dumps(
                    {**result.summary(), "answer": result.answer, "error": result.error},
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(result.answer)
            if args.stats:
                print("\n--- run stats ---", file=sys.stderr)
                for k, v in result.summary().items():
                    print(f"{k:>14}: {v}", file=sys.stderr)
        return 0 if result.ok else 1


async def cmd_tools(args: argparse.Namespace) -> int:
    agent = build_agent(load_settings(args.config), enable_memory=False)
    async with agent:
        for spec in agent.registry.specs():
            verdict = agent.engine.policy.decide(spec.name, {})
            print(
                f"{spec.name:<14} risk={spec.risk.value:<8} "
                f"policy={verdict.decision.value:<9} {spec.description[:60]}"
            )
    return 0


async def cmd_config(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    payload = asdict(settings)
    payload["provider"]["api_key"] = "***" if settings.provider.api_key else ""
    print(json.dumps(payload, indent=2, default=list))
    return 0


async def cmd_health(args: argparse.Namespace) -> int:
    settings = load_settings(args.config)
    agent = build_agent(settings)
    report: dict[str, Any] = {
        "version": __version__,
        "provider": settings.provider.kind,
        "base_url": settings.provider.base_url,
    }
    async with agent:
        try:
            r = await agent.ask(
                "Reply with the single word: ok", budget=Budget(max_steps=3, max_seconds=30)
            )
            report["provider_reachable"] = r.ok
            report["sample"] = r.answer[:80]
        except AegisError as exc:
            report["provider_reachable"] = False
            report["error"] = str(exc)
        if agent.memory:
            try:
                report["memory"] = await agent.memory.health()
            except Exception as exc:
                report["memory"] = {"error": str(exc)}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report.get("provider_reachable") else 1


async def cmd_harness_inspect(args: argparse.Namespace) -> int:
    """Show the current Continual Harness entries and refinement history."""
    ctrl = HarnessController(args.path)
    state = ctrl.state
    total = sum(len(v) for v in state.entries.values())
    print(f"# Continual Harness ({args.path})")
    print(f"entries: {total}  | refinements: {len(state.refinements)}")
    print("")
    for kind in ("prompt", "memory", "skill", "subagent"):
        entries = list(state.entries[kind].values())
        if not entries:
            continue
        print(f"## {kind} ({len(entries)})")
        for e in entries:
            print(f"- [{e.scope}:{e.id}] v{e.version} {e.title}: {e.content[:160]}")
    if state.refinements:
        print("\n## refinement history")
        for ev in state.refinements:
            tag = " [grounded]" if ev.grounded else ""
            changes = ", ".join(ev.changes) or "no applied edits"
            print(f"- [{ev.id}]{tag} {ev.trigger}: {changes}")
    return 0


async def cmd_harness_rollback(args: argparse.Namespace) -> int:
    """Roll back a prior refinement by id (reverts every applied edit)."""
    ctrl = HarnessController(args.path)
    target = None
    for ev in ctrl.state.refinements:
        if ev.id == args.refinement:
            from .memory.harness import AppliedRefinementEdit, RefinementResult

            applied = [
                AppliedRefinementEdit(
                    action=d.get("action", "create"),
                    kind=d.get("kind", "memory"),
                    id=d.get("id", ""),
                    title=d.get("title"),
                    content=d.get("content"),
                    path=d.get("path"),
                    reference=d.get("reference"),
                    arguments=d.get("arguments"),
                    metadata=d.get("metadata"),
                    reason=d.get("reason"),
                    applied=bool(d.get("applied", True)),
                    before=_entry_from_dict(d.get("before")) if d.get("before") else None,
                    after=_entry_from_dict(d.get("after")) if d.get("after") else None,
                    error=d.get("error"),
                )
                for d in ev.detail
            ]
            target = RefinementResult(
                id=ev.id,
                summary=ev.trigger,
                rationale="",
                expected_outcome=ev.outcome,
                applied_edits=applied,
                scope="global",
                grounded=ev.grounded,
            )
            break
    if target is None:
        print(f"error: no refinement with id {args.refinement}", file=sys.stderr)
        return 1
    result = ctrl.rollback(target)
    print(f"rolled back {args.refinement}: {len(result.applied_edits)} edit(s) reverted")
    return 0


def _entry_from_dict(d: dict[str, Any]) -> HarnessEntry:
    return HarnessEntry(**{k: d[k] for k in HarnessEntry.__dataclass_fields__ if k in d})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aegis", description="Aegis Zero agentic runtime")
    p.add_argument("--version", action="version", version=f"aegis-zero {__version__}")
    p.add_argument("-c", "--config", help="path to a YAML config file")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the agent on a goal")
    run.add_argument("goal")
    run.add_argument("-m", "--model", help="override fast and deep models")
    run.add_argument(
        "--approve",
        choices=("console", "auto", "deny"),
        default="console",
        help="approval gate for risky tools",
    )
    run.add_argument("--max-steps", type=int, default=24)
    run.add_argument("--timeout", type=float, default=600.0)
    run.add_argument("--no-memory", action="store_true")
    run.add_argument("--json", action="store_true")
    run.add_argument("--stats", action="store_true")
    run.add_argument("-v", "--verbose", action="store_true")
    run.set_defaults(fn=cmd_run)

    tools = sub.add_parser("tools", help="list tools and their policy verdicts")
    tools.set_defaults(fn=cmd_tools)

    cfg = sub.add_parser("config", help="show effective configuration")
    cfg.set_defaults(fn=cmd_config)

    health = sub.add_parser("health", help="check provider and memory health")
    health.set_defaults(fn=cmd_health)

    harness = sub.add_parser("harness", help="inspect and manage the Continual Harness")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    inspect = harness_sub.add_parser("inspect", help="show entries and refinement history")
    inspect.add_argument("--path", required=True, help="harness_state.json path")
    inspect.set_defaults(fn=cmd_harness_inspect)
    rollback = harness_sub.add_parser("rollback", help="revert a refinement by id")
    rollback.add_argument("--path", required=True, help="harness_state.json path")
    rollback.add_argument("--refinement", required=True, help="refinement id to revert")
    rollback.set_defaults(fn=cmd_harness_rollback)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except AegisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
