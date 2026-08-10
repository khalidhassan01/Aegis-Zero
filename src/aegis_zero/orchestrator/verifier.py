"""Deterministic verifiers that ground the Auditor in external signal.

The original auditor was pure LLM self-critique (Huang et al., ICLR 2024:
intrinsic self-correction is neutral-to-harmful). These checks run *before*
the LLM auditor and force a revision on hard, checkable failures, passing the
concrete failure to the revisor instead of prose.

A verifier returns ``CheckResult`` objects. ``hard`` failures (the answer
contradicts something the run itself established) block acceptance; ``soft``
failures are advisory notes handed to the LLM auditor.

The module is dependency-free and fully unit-testable without any LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"-?\d[\d_,]*\.?\d*")
_NUM_IN_WORD = re.compile(r"\b(\d[\d_,]*)\b")


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    hard: bool
    detail: str = ""

    @property
    def severity(self) -> str:
        return "hard" if self.hard else "soft"


@dataclass(slots=True)
class Verification:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True only if no *hard* check failed."""
        return not any(not c.passed and c.hard for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]

    @property
    def hard_failures(self) -> list[CheckResult]:
        return [c for c in self.failures if c.hard]

    @property
    def report(self) -> str:
        if not self.failures:
            return ""
        return "\n".join(f"- [{c.severity}] {c.name}: {c.detail}" for c in self.failures)


def _nums(text: str) -> list[str]:
    return [m.group(0) for m in _NUM.finditer(text or "")]


def _to_float(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


def verify_arithmetic(goal: str, answer: str) -> CheckResult:
    """Check that arithmetic the answer performs actually evaluates.

    Extracts expressions of the form `a <op> b = c` and confirms c equals the
    computed value. This catches the classic self-correction failure where the
    model states a wrong total (e.g. Neptune vs Uranus diameters).
    """
    pattern = re.compile(
        r"([\d][\d_,]*\.?\d*)\s*"
        r"([+\-*/^]|to the power of|\*\*)\s*"
        r"([\d][\d_,]*\.?\d*)\s*"
        r"(?:=|is|equals|results? in|gives?|=>)\s*"
        r"([\d][\d_,]*\.?\d*)"
    )
    bad: list[str] = []
    for m in pattern.finditer(answer):
        a = _to_float(m.group(1))
        b = _to_float(m.group(3))
        claimed = _to_float(m.group(4))
        if a is None or b is None or claimed is None:
            continue
        op = m.group(2)
        actual: float | None = None
        if op in ("+",):
            actual = a + b
        elif op == "-":
            actual = a - b
        elif op in ("*", "x", "X"):
            actual = a * b
        elif op in ("/",):
            actual = a / b if b else None
        elif op in ("^", "to the power of", "**"):
            actual = a**b if b < 50 else None
        else:
            actual = None
        if actual is None:
            continue
        # tolerate rounding to the same integer / two decimals
        if abs(actual - claimed) > max(1.0, abs(actual) * 1e-3):
            bad.append(
                f"{m.group(1)} {op} {m.group(3)} should be {actual:g}, answer says {claimed:g}"
            )

    if bad:
        return CheckResult(
            "arithmetic", False, True, "; ".join(bad[:3]) + ("..." if len(bad) > 3 else "")
        )
    return CheckResult("arithmetic", True, True, "")


def verify_tool_consistency(answer: str, tool_results: list) -> CheckResult:
    """Check the answer does not contradict what tools actually returned.

    For each numeric value a tool emitted, if the answer states a conflicting
    number for the same quantity we cannot always know it is the same quantity,
    so this is *soft*: it flags plausible mismatches for the auditor rather
    than asserting identity. A tool value that appears verbatim in the answer
    is treated as consistent.
    """
    tool_nums = set()
    for res in tool_results:
        text = getattr(res, "output", None) or getattr(res, "content", "") or ""
        for n in _nums(text):
            f = _to_float(n)
            if f is not None:
                tool_nums.add(round(f, 2))

    if not tool_nums:
        return CheckResult("tool_consistency", True, False, "no numeric tool output to check")

    mismatches: list[str] = []
    for n in _nums(answer):
        f = _to_float(n)
        if f is None:
            continue
        r = round(f, 2)
        # A claimed number that is not close to any tool value is suspicious
        # when the task clearly depended on a tool result.
        if not any(abs(r - t) <= max(1.0, abs(t) * 1e-3) for t in tool_nums):
            mismatches.append(str(n))
    if mismatches:
        return CheckResult(
            "tool_consistency",
            False,
            False,
            "answer numbers not seen in tool output: " + ", ".join(mismatches[:5]),
        )
    return CheckResult("tool_consistency", True, False, "")


def verify_json_valid(text: str) -> CheckResult:
    """If the answer contains a fenced JSON block, it must parse."""
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fence.group(1) if fence else text.strip()
    if "{" not in candidate and "[" not in candidate:
        return CheckResult("json_valid", True, False, "no JSON to validate")
    try:
        import json

        json.loads(candidate)
        return CheckResult("json_valid", True, False, "")
    except ValueError as exc:
        return CheckResult("json_valid", False, True, f"JSON parse error: {exc}")


def run_default_checks(
    goal: str, answer: str, tool_results: list | None = None
) -> Verification:
    """The standard verification battery used by the engine."""
    checks = [
        verify_arithmetic(goal, answer),
        verify_json_valid(answer),
    ]
    if tool_results:
        checks.append(verify_tool_consistency(answer, tool_results))
    return Verification(checks=checks)
