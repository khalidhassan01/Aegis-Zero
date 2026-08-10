"""Grounded extraction gate tests.

This is the piece prime-agent lacks: a refinement proposal is built from a
*verified outcome signal* (the deterministic verifier + task success), not
from the model's own narrative. The gate decides whether a successful run
left behind a durable lesson worth persisting.
"""

from __future__ import annotations

from aegis_zero.memory.harness_extraction import (
    ExtractionDecision,
    decide_extraction,
    propose_from_outcome,
)
from aegis_zero.orchestrator.verifier import Verification, CheckResult


def _verification(ok: bool) -> Verification:
    return Verification(checks=[CheckResult("arithmetic", ok, True)])


def test_successful_verified_run_yields_grounded_proposal():
    decision = decide_extraction(
        goal="Summarize the deploy run",
        answer="Logs attached.",
        verification=_verification(ok=True),
        run_ok=True,
        confidence=0.9,
    )
    assert decision.should_refine is True
    assert decision.grounded is True
    proposal = propose_from_outcome(
        goal="Summarize the deploy run",
        answer="Logs attached.",
        verification=_verification(ok=True),
        run_ok=True,
        confidence=0.9,
    )
    assert proposal.grounded is True
    assert "deploy" in proposal.summary.lower() or proposal.edits
    # The lesson is stored as a durable memory, scoped global (verified, reusable).
    assert any(e.kind == "memory" for e in proposal.edits)


def test_failed_verifier_suppresses_extraction():
    decision = decide_extraction(
        goal="Compute 2+2",
        answer="It is 5.",
        verification=_verification(ok=False),
        run_ok=True,
        confidence=0.2,
    )
    assert decision.should_refine is False
    assert decision.grounded is False
    assert "verifier" in decision.reason.lower()
