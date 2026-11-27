"""Pin examples/smart_services.py to the engine behaviour it promises.

The smart-services flow is a recruiter-facing artifact: it must keep
proving, on every CI run, that a free-text onboarding email becomes a
typed record; that low-risk provisioning is automatic; that restricted
zones route to a human sign-off; and that the audit-log opt-out is
denied by policy — with reasons everywhere.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from aegis_zero.core.models import Decision

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    """Import a repo file by path (examples/ is not a package)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


smart_services = _load("smart_services", REPO / "examples" / "smart_services.py")


def test_extraction_returns_the_typed_record() -> None:
    record = smart_services._extract(smart_services.EMAIL)
    assert record["person"] == "Tomas Weber"
    assert record["zones"] == ["office-muc-3", "lab-b", "server-room"]
    assert record["time_profile"] == "flextime"
    assert record["flags"] == {"temporary_admin": True, "disable_audit_log": True}


def test_flow_grants_rejects_and_denies_exactly_as_promised() -> None:
    report = asyncio.run(smart_services.run_flow())
    results = report.result.tool_results
    assert len(results) == 7

    # 1-4 execute: parse, office access, time profile, approved lab access.
    assert [r.ok for r in results] == [True, True, True, True, False, False, False]

    assert results[1].output["zone"] == "office-muc-3"
    assert results[1].output["via"] == "self-service automation"
    assert results[2].output["profile"] == "flextime"
    assert results[3].output["zone"] == "lab-b"
    assert results[3].output["via"] == "service-desk sign-off"

    # 5-6 are rejected by the service desk, with the verdict recorded.
    assert results[4].error == "human approval denied"
    assert results[4].decision is Decision.DENY
    assert results[5].error == "human approval denied"
    assert results[5].decision is Decision.DENY

    # 7 never even reaches a human: policy denies it outright.
    assert results[6].error == "policy denied: tool explicitly denied by configuration"
    assert results[6].decision is Decision.DENY


def test_service_desk_only_saw_the_three_sensitive_requests() -> None:
    report = asyncio.run(smart_services.run_flow())
    log = "\n".join(report.reviewer_log)
    assert len(report.reviewer_log) == 3
    assert "lab-b → APPROVE" in log
    assert "server-room → REJECT" in log
    assert "create_temporary_admin · Tomas Weber → REJECT" in log


def test_answer_reports_the_outcome_honestly() -> None:
    report = asyncio.run(smart_services.run_flow())
    answer = report.result.answer
    assert report.result.ok is True
    assert "onboarded" in answer
    assert "audit-log" in answer
    assert "least privilege" in answer
