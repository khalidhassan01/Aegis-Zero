"""Thirty-second offline demo: the real policy engine and orchestrator, no model.

Every line this script prints is produced by live Aegis Zero code — nothing is
hard-coded prose. The policy verdicts come from ``PolicyEngine.decide()`` and
the run stats from a deterministic ``AgentEngine`` pass driven by the scripted
``EchoProvider`` (the same mechanism the test suite uses), so the demo needs
no model server, no API key, and no network.

``scripts/make_demo.py`` turns this transcript into ``docs/demo.svg`` and
``docs/demo.cast``; ``tests/test_demo_assets.py`` pins those artifacts to the
code so the demo cannot silently drift.
"""

from __future__ import annotations

import asyncio

from aegis_zero import __version__
from aegis_zero.orchestrator import AgentEngine, EngineConfig
from aegis_zero.providers import EchoProvider, scripted_tool_call
from aegis_zero.tools import AutoApprove, PolicyEngine, default_registry

Line = tuple[str, str]
"""A demo line: ``(kind, text)`` with kind in cmd/hdr/out/ok/warn/deny/dim/sp."""

GOAL = "What is six times seven?"
EXPRESSION = "6*7"

# (tool, real arguments, cosmetic label shown in the demo)
PROBES: list[tuple[str, dict, str]] = [
    (
        "http_fetch",
        {"url": "http://169.254.169.254/latest/meta-data"},
        "http://169.254.169.254/latest/meta-data",
    ),
    ("read_file", {"path": "/home/dev/.ssh/id_rsa"}, "/home/dev/.ssh/id_rsa"),
    ("shell", {"command": "rm -rf /"}, "rm -rf /"),
    (
        "http_fetch",
        {
            "url": "https://api.example.com/v1",
            "headers": {"authorization": "Bearer sk-demo0123456789abcdef"},
        },
        "https://api.example.com · Authorization: Bearer sk-…",
    ),
]


def _policy() -> PolicyEngine:
    """Deterministic offline policy engine (no DNS lookups)."""

    def resolve(host: str) -> list[str]:
        # Link-local metadata IP passes through; every other host resolves to
        # a public address so the URL guard's allow path is exercised offline.
        return [host] if host == "169.254.169.254" else ["93.184.216.34"]

    return PolicyEngine(resolve_host=resolve)


def _policy_lines() -> list[Line]:
    policy = _policy()
    lines: list[Line] = [("hdr", "── policy gate ── every tool call is judged before it runs")]
    for tool, args, label in PROBES:
        verdict = policy.decide(tool, args)
        lines.append(("out", f"{tool:<12} {label}"))
        kind = {"allow": "ok", "sanitize": "warn", "approve": "warn", "deny": "deny"}[
            verdict.decision.value
        ]
        detail = verdict.reason or f"risk tier {verdict.risk.value}"
        if verdict.redactions:
            detail = f"{verdict.reason} ({', '.join(verdict.redactions)})"
        lines.append((kind, f"{'':<13}{verdict.decision.value.upper()} · {detail}"))
    return lines


async def _run() -> tuple[str, list[Line]]:
    provider = EchoProvider(
        script=[
            scripted_tool_call("calculate", {"expression": EXPRESSION}),
            "The answer is 42.",
            '{"verdict":"pass","confidence":0.95,"issues":[]}',
        ]
    )
    engine = AgentEngine(
        provider,
        registry=default_registry(),
        approval=AutoApprove(),
        config=EngineConfig(fast_model="echo-1", deep_model="echo-1"),
    )
    result = await engine.run(GOAL)
    stats = result.summary()
    run_lines: list[Line] = [
        ("hdr", "── deterministic run ── scripted provider, real engine"),
        ("out", f"goal: {GOAL}"),
        ("ok", f"forge → calculate('{EXPRESSION}') → {result.tool_results[0].output}"),
        ("out", f"answer: {result.answer}"),
        (
            "ok",
            f"audit: {'pass' if result.ok else 'fail'} · confidence {stats['confidence']}",
        ),
        (
            "dim",
            "stats: steps {steps} · revisions {revisions} · tokens {tokens} "
            "· tool_calls {tool_calls}".format(**stats),
        ),
    ]
    return result.answer, run_lines


def transcript() -> list[Line]:
    """Build the full demo transcript from live engine behaviour."""

    async def build() -> list[Line]:
        answer, run_lines = await _run()
        assert answer == "The answer is 42.", answer
        return run_lines

    run_lines = asyncio.run(build())
    return [
        ("dim", f"Aegis Zero v{__version__} · offline demo · no model server, no network"),
        ("sp", ""),
        ("cmd", "python examples/demo.py"),
        ("sp", ""),
        *_policy_lines(),
        ("sp", ""),
        *run_lines,
        ("sp", ""),
        ("dim", "real engine output — reproduce with: python examples/demo.py"),
    ]


def main() -> int:
    for _, text in transcript():
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
