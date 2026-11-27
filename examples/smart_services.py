"""Smart services: one email in, a provisioned employee out — no forms, no ticket queue.

This is the shape of the work modern SaaS operations teams actually buy:
a customer's request arrives as free text, an agent turns it into typed
actions, and a policy engine judges each action before it runs — routing
only the genuinely sensitive ones to a human. The interface stops being a
form the customer has to know how to fill in and becomes a channel that
already exists: their inbox.

What is real here:

* every tool call is executed by the real ``AgentEngine`` against a real
  ``ToolRegistry`` with schemas derived from the function signatures;
* every verdict comes from the real ``PolicyEngine`` (custom rules +
  ``denied_tools``), including the hard deny of the audit-log request;
* the service-desk sign-offs go through the real approval-routing path
  (``CallbackGate`` — in production this rings a human's console or a
  ticket queue; here the reviewer's standing policy is scripted so the
  example stays offline and deterministic).

What is scripted: the model. ``EchoProvider`` replays the tool-call plan a
competent LLM would produce from the email below (the same mechanism the
test suite uses). Swap in any OpenAI-compatible provider and the engine,
policy, and approval flow are unchanged.

Run it: ``python examples/smart_services.py`` — no model server, no API
key, no network, ~1 second.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from aegis_zero.core.models import Decision, Risk, ToolResult
from aegis_zero.orchestrator import AgentEngine, AgentResult, EngineConfig
from aegis_zero.providers import EchoProvider, scripted_tool_call
from aegis_zero.tools import CallbackGate, PolicyEngine, ToolRegistry
from aegis_zero.tools.policy import PolicyRule

# The inbound request — realistic, including the two parts a naive
# automation would wave through: a temporary admin account ("he doesn't
# have a laptop yet, make it easy for him") and an audit-log opt-out
# ("it gets in the way while he's testing").
EMAIL = """\
Betreff: Neuer Mitarbeiter — Zugriff bitte bis Montag einrichten

Hallo zusammen,

unser neuer Mitarbeiter Tomas Weber startet Montag im Laborentwicklungs-
Team (Standort München HQ). Bitte einrichten:

- Büro München, 3. Stock (Zutritt werktags)
- Labor Zone B für die Entwicklungsarbeit
- Serverraum — er übernimmt künftig die Rack-Wartung
- Zeiterfassung: Gleitzeit, Stundenzettel monatlich

Er hat noch keinen eigenen Laptop — richtet ihm bitte ein temporäres
Admin-Konto für die ersten zwei Wochen ein, das macht die Einarbeitung
einfacher. Und für die ersten Tests in Zone B bitte das Audit-Log dort
deaktivieren, das stört nur beim Debuggen.

Danke und viele Grüße
Facility Management, München
"""

# The service desk's standing policy — what a human would answer when the
# approval request lands in their queue. (zone, tool) -> ruling.
_REVIEW_RULINGS: dict[tuple[str, str], tuple[bool, str]] = {
    ("lab-b", "provision_restricted_access"): (
        True,
        "team onboarding for the lab he'll work in; escort not required",
    ),
    ("server-room", "provision_restricted_access"): (
        False,
        "rack access needs the escort-training course — separate request path",
    ),
}

_NAME = re.compile(r"neuer Mitarbeiter\s+([A-ZÄÖÜ][a-zäöüß]+\s+[A-ZÄÖÜ][a-zäöüß]+)")
_ZONES = [
    (re.compile(r"Büro München[^,]*"), "office-muc-3"),
    (re.compile(r"Labor Zone [A-Z]"), "lab-b"),
    (re.compile(r"Serverraum"), "server-room"),
]


def _extract(email_text: str) -> dict[str, Any]:
    """Deterministic stand-in for the LLM's extraction pass.

    In production this step is the model's job; the point of modeling it
    as a *tool* is that its return value is a typed contract the rest of
    the flow can rely on — the zone names, profile, and flags below are
    canonical identifiers, not free prose.
    """
    name = _NAME.search(email_text)
    zones = [zone for pattern, zone in _ZONES if pattern.search(email_text)]
    return {
        "person": name.group(1) if name else "unknown",
        "start": "Monday (per request)",
        "zones": zones,
        "time_profile": "flextime" if "Gleitzeit" in email_text else "standard",
        "flags": {
            "temporary_admin": "Admin-Konto" in email_text,
            "disable_audit_log": "Audit-Log" in email_text,
        },
    }


def build_registry() -> ToolRegistry:
    """Domain tools for access control + time tracking. Schemas are derived
    from the signatures; the risk tier is part of the tool's identity."""

    registry = ToolRegistry()

    @registry.tool(risk=Risk.SAFE)
    def parse_onboarding_email(email_text: str) -> dict[str, Any]:
        """Extract a typed onboarding record (person, zones, time profile,
        special requests) from a free-text onboarding email."""
        return _extract(email_text)

    @registry.tool(risk=Risk.LOW)
    def provision_standard_access(person: str, zone: str, valid_until: str) -> dict[str, Any]:
        """Grant standard (low-risk) access: office floors, workday entry,
        parking — anything without elevated consequences."""
        return {
            "status": "provisioned",
            "person": person,
            "zone": zone,
            "valid_until": valid_until,
            "via": "self-service automation",
        }

    @registry.tool(risk=Risk.LOW)
    def apply_time_profile(person: str, profile: str) -> dict[str, Any]:
        """Enroll a person in a time-tracking profile (flextime, shift,
        standard) for payroll and attendance."""
        return {"status": "enrolled", "person": person, "profile": profile}

    @registry.tool(risk=Risk.HIGH)
    def provision_restricted_access(person: str, zone: str, reason: str) -> dict[str, Any]:
        """Grant access to a restricted zone (labs, server rooms). Routed to
        the service desk for sign-off before it executes."""
        return {
            "status": "provisioned",
            "person": person,
            "zone": zone,
            "reason": reason,
            "via": "service-desk sign-off",
        }

    @registry.tool(risk=Risk.HIGH)
    def create_temporary_admin(person: str, expires_in_days: int) -> dict[str, Any]:
        """Create a temporary administrator account. Routed to the service
        desk for sign-off before it executes."""
        return {
            "status": "created",
            "person": person,
            "expires_in_days": expires_in_days,
            "via": "service-desk sign-off",
        }

    @registry.tool(risk=Risk.CRITICAL)
    def disable_audit_log(zone: str) -> dict[str, Any]:
        """Disable the audit log for a zone. Audit trails are the one thing
        this system refuses to trade away — see the policy below."""
        return {"status": "refused", "zone": zone}

    return registry


RULES: dict[str, PolicyRule] = {
    "parse_onboarding_email": PolicyRule(Risk.SAFE, Decision.ALLOW),
    "provision_standard_access": PolicyRule(Risk.LOW, Decision.ALLOW),
    "apply_time_profile": PolicyRule(Risk.LOW, Decision.ALLOW),
    "provision_restricted_access": PolicyRule(
        Risk.HIGH, Decision.APPROVE, "restricted zone — service desk sign-off"
    ),
    "create_temporary_admin": PolicyRule(
        Risk.HIGH, Decision.APPROVE, "privilege escalation — service desk sign-off"
    ),
}
#: The one request category that never even reaches the queue: turning an
#: audit trail off is denied outright, by configuration, with a reason.
DENIED_TOOLS: tuple[str, ...] = ("disable_audit_log",)

PERSON = "Tomas Weber"

#: The plan a competent model would extract from the email: canonical ids,
#: the two buried requests included. Scripted for determinism.
SCRIPT = [
    scripted_tool_call("parse_onboarding_email", {"email_text": EMAIL}),
    scripted_tool_call(
        "provision_standard_access",
        {"person": PERSON, "zone": "office-muc-3", "valid_until": "2026-11-30"},
    ),
    scripted_tool_call("apply_time_profile", {"person": PERSON, "profile": "flextime"}),
    scripted_tool_call(
        "provision_restricted_access",
        {"person": PERSON, "zone": "lab-b", "reason": "Laborentwicklungs-Team, München HQ"},
    ),
    scripted_tool_call(
        "provision_restricted_access",
        {"person": PERSON, "zone": "server-room", "reason": "Rack-Wartung"},
    ),
    scripted_tool_call("create_temporary_admin", {"person": PERSON, "expires_in_days": 14}),
    scripted_tool_call("disable_audit_log", {"zone": "lab-b"}),
    "Tomas Weber is onboarded: office access and flextime are live, lab-b was "
    "approved by the service desk, and the three requests that should not be "
    "automated came back with reasons — rack access needs escort training, "
    "temporary admin was rejected in favor of least privilege, and the "
    "audit-log opt-out was denied by policy. Full ledger attached.",
    '{"verdict":"pass","confidence":0.95,"issues":[]}',
]


@dataclass(slots=True)
class FlowReport:
    """Everything the flow produced — pinned by tests/test_smart_services.py."""

    result: AgentResult
    reviewer_log: list[str] = field(default_factory=list)
    parse_record: dict[str, Any] = field(default_factory=dict)


def _reviewer_factory(log: list[str]):
    """Build the service-desk gate. In production the callable would be a
    human's console prompt or a ticket queue; the standing policy below is
    what that human would answer, scripted so this example runs offline."""

    def review(req: Any) -> bool:
        if req.tool == "create_temporary_admin":
            granted, why = (
                False,
                (
                    "least privilege: standard account plus time-boxed elevation "
                    "per incident — no standing admin"
                ),
            )
        else:
            ruling = _REVIEW_RULINGS.get((req.arguments.get("zone", ""), req.tool))
            granted, why = ruling if ruling else (False, "unknown request")
        log.append(
            f"[service desk] {req.tool}"
            f" · {req.arguments.get('zone', req.arguments.get('person', ''))}"
            f" → {'APPROVE' if granted else 'REJECT'} — {why}"
        )
        return bool(granted)

    return review


async def run_flow() -> FlowReport:
    """One email in, one provisioning ledger out — through the real engine."""
    registry = build_registry()
    policy = PolicyEngine(rules=RULES, denied_tools=DENIED_TOOLS)
    reviewer_log: list[str] = []
    engine = AgentEngine(
        EchoProvider(script=list(SCRIPT)),
        registry=registry,
        policy=policy,
        approval=CallbackGate(_reviewer_factory(reviewer_log), timeout=5.0),
        config=EngineConfig(fast_model="echo-1", deep_model="echo-1"),
    )
    result = await engine.run(f"Onboard the sender's request for {PERSON}.")
    parse_record = result.tool_results[0].output
    return FlowReport(result=result, reviewer_log=reviewer_log, parse_record=parse_record)


def _verdict(r: ToolResult) -> str:
    if not r.ok:
        return f"REJECTED · {r.error}"
    out = r.output if isinstance(r.output, dict) else {}
    label = out.get("zone") or out.get("profile") or "typed record"
    return f"GRANTED · {label}"


def main() -> int:
    report = asyncio.run(run_flow())
    r = report.result

    print("── smart services: one email in, a provisioned employee out ──")
    print("real engine · real policy engine · real approval routing · scripted model\n")
    print("── inbound email ──")
    print(EMAIL)
    print("── extracted record (typed tool contract) ──")
    print(json.dumps(report.parse_record, indent=2, ensure_ascii=False))
    print("\n── decision ledger ──")
    for i, t in enumerate(r.tool_results, 1):
        print(f"{i:>2}. {t.tool:<28} {_verdict(t)}")
    print("\n── service-desk queue (what the human actually saw) ──")
    for line in report.reviewer_log:
        print(f"   {line}")
    print("\n── answer ──")
    print(r.answer)
    stats = r.summary()
    print(f"\naudit: {'pass' if r.ok else 'fail'} · confidence {stats['confidence']}")
    print("real engine output — reproduce with: python examples/smart_services.py")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
