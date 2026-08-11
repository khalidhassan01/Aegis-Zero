"""Grounded extraction gate for the Continual Harness.

This is the part prime-agent's Continual Harness does not have. Prime Agent
decides whether to ``/refine`` with a second, *unverified* LLM call (the
auto-refine review gate), so a refinement is "good" because the model said
so. Here the decision is driven by an **outcome signal** we already trust:
Aegis-Zero's deterministic verifier (verifier.py) and the task success flag.

A lesson is only extracted when:
  - the run succeeded (``result.ok``), AND
  - no hard verifier check failed, AND
  - confidence clears a floor,
otherwise extraction is suppressed and any prior lesson on the same topic is
left untouched. The resulting proposal is marked ``grounded=True`` so it is
visibly distinguished from free-form, model-authored refinements.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..orchestrator.verifier import Verification
from .harness import RefinementEdit, RefinementProposal

# Below this confidence we do not trust the run enough to generalize a lesson.
_MIN_CONFIDENCE = 0.6


@dataclass(slots=True)
class ExtractionDecision:
    should_refine: bool
    grounded: bool
    reason: str


def decide_extraction(
    *,
    goal: str,
    answer: str,
    verification: Verification,
    run_ok: bool,
    confidence: float,
) -> ExtractionDecision:
    """Decide whether a successful run left a durable, reusable lesson.

    Pure function of the outcome signal -- no LLM call, so it cannot be
    gamed by the model narrating its own success.
    """
    if not run_ok:
        return ExtractionDecision(False, False, "run did not succeed")
    if verification.hard_failures:
        return ExtractionDecision(False, False, "verifier hard check failed")
    if confidence < _MIN_CONFIDENCE:
        return ExtractionDecision(
            False, False, f"confidence {confidence:.2f} below floor {_MIN_CONFIDENCE}"
        )
    return ExtractionDecision(True, True, "verified success; lesson eligible for extraction")


def propose_from_outcome(
    *,
    goal: str,
    answer: str,
    verification: Verification,
    run_ok: bool,
    confidence: float,
    scope: str = "global",
) -> RefinementProposal:
    """Build a small, evidence-backed, GROUNDED refinement proposal.

    Keeps the lesson scoped to a single durable memory entry (the smallest
    useful unit), recording the verifier evidence so rollback/history is
    auditable. We deliberately do not let the model expand this into many
    edits -- that is the LLM-narrative trap we are avoiding.
    """
    decision = decide_extraction(
        goal=goal,
        answer=answer,
        verification=verification,
        run_ok=run_ok,
        confidence=confidence,
    )
    if not decision.should_refine:
        # Return an empty, explicitly non-grounded proposal so callers can
        # still record "no lesson this turn" without special-casing None.
        return RefinementProposal(
            summary="no lesson extracted",
            rationale=decision.reason,
            expected_outcome="",
            edits=[],
            grounded=False,
            evidence="",
        )

    # Compact, durable summary of what was accomplished.
    summary = goal.strip().replace("\n", " ")[:120] or "completed task"
    evidence = verification.report or f"verifier passed; confidence {confidence:.2f}"
    content = f"[verified] {summary}"

    return RefinementProposal(
        summary=f"lesson: {summary}",
        rationale="extracted from a verified successful run",
        expected_outcome="reuse this lesson in future related runs",
        edits=[
            RefinementEdit(
                action="create",
                kind="memory",
                title=summary,
                content=content,
                path="verified-lessons",
                metadata={"confidence": round(confidence, 3), "run_ok": True},
            )
        ],
        grounded=True,
        evidence=evidence,
    )
