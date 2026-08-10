"""Specialist agents. Each is a focused role over the shared runtime."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..core.models import Completion, Complexity, Message

SCOUT_SYSTEM = """You are Scout, the reconnaissance agent in Aegis Zero.
Your job is to understand the problem before anyone acts on it.
Produce: the real underlying goal, key unknowns, constraints, and the
minimum set of facts needed to proceed. Be concise and concrete.
Never propose an implementation; that is Forge's job."""

FORGE_SYSTEM = """You are Forge, the execution agent in Aegis Zero.
You solve the task directly and completely, using tools when they help.
Prefer verified action over speculation: if a tool can confirm something,
call it rather than guessing. State assumptions explicitly."""

AUDITOR_SYSTEM = """You are Auditor, the adversarial reviewer in Aegis Zero.
Critique the candidate answer against the original request. Hunt for
factual errors, unverified claims, missed constraints, and safety issues.
Respond with strict JSON only:
{"verdict": "pass" | "revise" | "fail",
 "confidence": 0.0-1.0,
 "issues": ["..."],
 "suggestion": "concrete fix or empty string"}"""

PLANNER_SYSTEM = """You are the Planner in Aegis Zero. Decompose the goal
into independent, parallelizable subtasks. Respond with strict JSON only:
{"complexity": "trivial"|"simple"|"moderate"|"complex",
 "parallel": true|false,
 "subtasks": [{"id": "s1", "goal": "...", "depends_on": []}]}
Emit at most 5 subtasks. For a trivial or simple goal, emit exactly one."""


@dataclass(frozen=True, slots=True)
class Critique:
    verdict: str
    confidence: float
    issues: tuple[str, ...] = ()
    suggestion: str = ""

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"


@dataclass(frozen=True, slots=True)
class Subtask:
    id: str
    goal: str
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Plan:
    complexity: Complexity
    parallel: bool
    subtasks: tuple[Subtask, ...]

    @property
    def is_single(self) -> bool:
        return len(self.subtasks) <= 1


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response."""
    if not text:
        return {}
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?|```$", "", stripped,
                          flags=re.MULTILINE).strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        pass
    match = _JSON_BLOCK.search(stripped)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def parse_plan(completion: Completion, goal: str) -> Plan:
    data = extract_json(completion.text)
    raw_tasks = data.get("subtasks") or []
    tasks: list[Subtask] = []
    for i, item in enumerate(raw_tasks[:5]):
        if not isinstance(item, dict):
            continue
        sub_goal = str(item.get("goal") or "").strip()
        if not sub_goal:
            continue
        tasks.append(Subtask(
            id=str(item.get("id") or f"s{i + 1}"),
            goal=sub_goal,
            depends_on=tuple(str(d) for d in (item.get("depends_on") or [])),
        ))
    if not tasks:
        tasks = [Subtask(id="s1", goal=goal)]

    try:
        complexity = Complexity(str(data.get("complexity", "moderate")).lower())
    except ValueError:
        complexity = Complexity.MODERATE

    return Plan(complexity=complexity,
                parallel=bool(data.get("parallel", len(tasks) > 1)),
                subtasks=tuple(tasks))


def parse_critique(completion: Completion) -> Critique:
    data = extract_json(completion.text)
    verdict = str(data.get("verdict", "")).lower()
    if verdict not in ("pass", "revise", "fail"):
        # No parseable verdict: treat as a soft pass with low confidence
        # rather than silently claiming success.
        return Critique("revise", 0.3, ("auditor returned unparseable output",), "")
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    issues = tuple(str(i) for i in (data.get("issues") or []) if str(i).strip())
    return Critique(verdict, max(0.0, min(1.0, confidence)), issues,
                    str(data.get("suggestion") or ""))


def heuristic_complexity(goal: str) -> Complexity:
    """Cheap fallback classifier used when the planner is skipped."""
    text = goal.lower()
    words = len(text.split())
    signals = sum(text.count(t) for t in
                  (" and ", " then ", " also ", " after ", ";", "\n-", "1.", "2."))
    if words <= 5 and signals == 0:
        return Complexity.TRIVIAL
    if words <= 30 and signals <= 1:
        return Complexity.SIMPLE
    if signals >= 4 or words > 120:
        return Complexity.COMPLEX
    return Complexity.MODERATE


def scout_prompt(goal: str) -> list[Message]:
    return [Message(role="system", content=SCOUT_SYSTEM),
            Message(role="user", content=goal)]


def auditor_prompt(goal: str, answer: str) -> list[Message]:
    return [
        Message(role="system", content=AUDITOR_SYSTEM),
        Message(role="user",
                content=f"ORIGINAL REQUEST:\n{goal}\n\nCANDIDATE ANSWER:\n{answer}"),
    ]


def planner_prompt(goal: str) -> list[Message]:
    return [Message(role="system", content=PLANNER_SYSTEM),
            Message(role="user", content=goal)]
