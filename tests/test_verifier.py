"""Tests for the grounded verifier (P1) and its wiring into the engine.

The verifier is dependency-free and deterministic, so it is fully
unit-testable without an LLM. The wiring test confirms a hard check failure
forces a revision even when the auditor is satisfied.
"""

from __future__ import annotations

import pytest

from aegis_zero.core.models import ToolResult
from aegis_zero.orchestrator.verifier import (
    run_default_checks,
    verify_arithmetic,
    verify_json_valid,
    verify_tool_consistency,
)

# ----------------------------------------------------------- arithmetic


def test_correct_arithmetic_passes():
    ok = verify_arithmetic("x", "2 + 3 = 5 and 10 * 4 = 40").passed
    assert ok is True


def test_wrong_arithmetic_fails_hard():
    r = verify_arithmetic("x", "The total is 142984 + 120536 + 49244 = 312764")
    assert r.passed is False
    assert r.hard is True
    assert "312764" in r.detail


def test_arithmetic_catches_power():
    r = verify_arithmetic("x", "2 ^ 20 = 1048576")
    assert r.passed is True
    r2 = verify_arithmetic("x", "2 ^ 20 = 999999")
    assert r2.passed is False


def test_arithmetic_ignores_numbers_not_in_an_equation():
    # bare numbers with no operation should not trigger
    assert verify_arithmetic("x", "The answer is 42").passed is True


# ------------------------------------------------------------- json


def test_valid_json_passes():
    assert verify_json_valid('```json\n{"a": 1}\n```').passed is True


def test_invalid_json_fails_hard():
    r = verify_json_valid('```json\n{"a": }\n```')
    assert r.passed is False
    assert r.hard is True


def test_plain_text_has_no_json_to_check():
    assert verify_json_valid("just words").passed is True


# --------------------------------------------------- tool consistency


def test_answer_matching_tool_output_is_consistent():
    res = [ToolResult(tool="calculate", ok=True, output="1048576", duration_ms=1.0)]
    assert verify_tool_consistency("result is 1048576", res).passed is True


def test_answer_contradicting_tool_output_flagged_soft():
    res = [ToolResult(tool="calculate", ok=True, output="1048576", duration_ms=1.0)]
    r = verify_tool_consistency("result is 12345", res)
    assert r.passed is False
    assert r.hard is False  # soft: needs human/auditor judgement


def test_no_tool_output_is_neutral():
    assert verify_tool_consistency("answer 42", []).passed is True


# ------------------------------------------------------------ battery


def test_run_default_checks_aggregates():
    v = run_default_checks("g", '2 + 2 = 5 but json {"ok": true}')
    assert v.ok is False
    assert v.hard_failures  # arithmetic is hard
    assert any(c.name == "json_valid" for c in v.checks)


def test_verification_ok_when_all_pass():
    v = run_default_checks("g", "2 + 2 = 4 and no json here")
    assert v.ok is True
    assert v.report == ""


# --------------------------------------------------------- wiring


@pytest.mark.asyncio
async def test_hard_check_forces_revision_despite_pass_verdict():
    """Even if the auditor says 'pass', a wrong arithmetic total must be
    revised. This is the external-signal fix for intrinsic self-correction."""
    from aegis_zero.orchestrator.engine import AgentEngine, EngineConfig
    from aegis_zero.providers.echo import EchoProvider

    # Script: answer with a WRONG total, then auditor says 'pass',
    # then a corrected answer, then auditor says 'pass'.
    script = [
        'The total is 12 + 13 = 30. {"done": true}',
        '{"verdict": "pass", "confidence": 0.9, "issues": [], "suggestion": ""}',
        "The total is 12 + 13 = 25.",
        '{"verdict": "pass", "confidence": 0.9, "issues": [], "suggestion": ""}',
    ]
    engine = AgentEngine(
        EchoProvider(script=script),
        config=EngineConfig(enable_scout=False, enable_planning=False, temperature=0.0),
    )
    result = await engine.run("What is 12 + 13?")
    assert result.revisions >= 1, "verifier must have forced at least one revision"
    assert "25" in result.answer, "final answer should be the corrected one"
    assert result.critique is not None
