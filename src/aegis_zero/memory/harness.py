"""Continual Harness: the explicit, editable, rollbackable behavior layer.

This is the steal from Prime Intellect's ``prime-agent`` refinement model
(packages/coding-agent/src/core/refinement/), reimplemented for Aegis Zero
with our own discipline:

* The base system prompt is IMMUTABLE. Harness entries are supplemental
  context only, never a rewrite of the system prompt.
* Four entry kinds (prompt | memory | skill | subagent) scoped local
  (session) or global (cross-session).
* Every refinement records before/after per edit, so any refinement can be
  rolled back. Persistence is atomic (temp file + rename) and a corrupt
  state file degrades to empty instead of crashing the session.

Unlike prime-agent, our refinements can be *grounded*: a refinement carries an
optional ``evidence`` string and ``grounded`` flag so the engine can mark
whether the lesson came from a verified outcome (the verifier or a success
signal) rather than the model's own narrative. That closes prime-agent's
biggest weakness -- a refinement is "good" there because the model said so.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

from ..core.models import new_id

HarnessScope = Literal["local", "global"]
RefinementKind = Literal["prompt", "memory", "skill", "subagent"]
RefinementAction = Literal["create", "update", "delete"]

HARNESS_SCHEMA = 1

# Formatting budgets (kept close to prime-agent so behavior is predictable).
_DEFAULT_OVERVIEW_LIMIT = 6
_DEFAULT_REFINEMENT_LIMIT = 5
_DEFAULT_CONTENT_LIMIT = 180

# The one id that must never be editable: the immutable base system prompt.
_IMMUTABLE_BASE_ID = "base_system_prompt"


# -- data model ---------------------------------------------------------------


@dataclass(slots=True)
class HarnessEntry:
    id: str
    kind: RefinementKind
    title: str
    content: str
    scope: HarnessScope = "local"
    path: str = "general"
    reference: dict[str, Any] = field(default_factory=dict)
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = "refine"
    created_at: str = ""
    updated_at: str = ""
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HarnessRefinementEvent:
    id: str
    trigger: str
    changes: list[str]
    evidence: str
    outcome: str
    created_at: str
    grounded: bool = False
    detail: list[dict[str, Any]] = field(
        default_factory=list
    )  # serialized applied edits for exact rollback


@dataclass(slots=True)
class HarnessState:
    schema: int = HARNESS_SCHEMA
    entries: dict[str, dict[str, HarnessEntry]] = field(
        default_factory=lambda: {"prompt": {}, "memory": {}, "skill": {}, "subagent": {}}
    )
    refinements: list[HarnessRefinementEvent] = field(default_factory=list)


@dataclass(slots=True)
class RefinementEdit:
    action: RefinementAction
    kind: RefinementKind
    id: str | None = None
    title: str | None = None
    content: str | None = None
    path: str | None = None
    reference: dict[str, Any] | None = None
    arguments: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None


@dataclass(slots=True)
class RefinementProposal:
    summary: str
    rationale: str
    expected_outcome: str
    edits: list[RefinementEdit] = field(default_factory=list)
    grounded: bool = False
    evidence: str = ""


@dataclass(slots=True)
class AppliedRefinementEdit:
    action: RefinementAction
    kind: RefinementKind
    id: str = ""
    title: str | None = None
    content: str | None = None
    path: str | None = None
    reference: dict[str, Any] | None = None
    arguments: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    reason: str | None = None
    applied: bool = False
    before: HarnessEntry | None = None
    after: HarnessEntry | None = None
    error: str | None = None


@dataclass(slots=True)
class RefinementResult:
    id: str
    summary: str
    rationale: str
    expected_outcome: str
    applied_edits: list[AppliedRefinementEdit] = field(default_factory=list)
    harness_state_path: str = ""
    rollback_of: str | None = None
    scope: HarnessScope | None = None
    grounded: bool = False


# -- helpers -----------------------------------------------------------------


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _slug(raw: str, fallback: str) -> str:
    normalized = raw.strip().lower().replace(" ", "_")
    normalized = "".join(c if (c.isalnum() or c == "_") else "_" for c in normalized)
    normalized = normalized.strip("_")[:80]
    return normalized or fallback


def _clone(entry: HarnessEntry | None) -> HarnessEntry | None:
    return replace(entry) if entry else None


# -- apply / rollback ---------------------------------------------------------


def apply_refinement_proposal(
    state: HarnessState,
    proposal: RefinementProposal,
    *,
    options: dict[str, Any],
) -> RefinementResult:
    """Apply edits in-place, recording before/after for each.

    Returns a RefinementResult listing every edit and whether it applied.
    Mirrors prime-agent's ``applyRefinementProposal``: invalid edits are
    recorded as not-applied with a reason rather than raising, so one bad
    edit never sinks the whole refinement.
    """
    scope: HarnessScope = options.get("scope", "local")
    baseline: HarnessState | None = options.get("baseline_state")
    applied: list[AppliedRefinementEdit] = []
    modified_keys: set[str] = set()

    for edit in proposal.edits:
        computed_id = edit.id or (
            _slug(edit.title or edit.kind, edit.kind) if edit.action == "create" else ""
        )
        err = _validate_edit(edit, computed_id)
        if err:
            applied.append(_rejected(edit, computed_id, err))
            continue

        records = state.entries[edit.kind]
        before = _clone(records.get(computed_id))
        key = f"{edit.kind}:{computed_id}"

        # Concurrent-mutation guard: if a baseline was supplied and the entry
        # changed since planning, refuse to apply (would clobber a newer edit).
        if baseline is not None and key not in modified_keys:
            base_before = baseline.entries.get(edit.kind, {}).get(computed_id)
            if json.dumps(asdict(before) if before else None, sort_keys=True) != json.dumps(
                asdict(base_before) if base_before else None, sort_keys=True
            ):
                applied.append(
                    _rejected(edit, computed_id, "entry changed during refinement planning")
                )
                continue

        if edit.action == "delete":
            if before is None:
                applied.append(_rejected(edit, computed_id, "entry not found"))
                continue
            del records[computed_id]
            modified_keys.add(key)
            applied.append(
                AppliedRefinementEdit(
                    **_base_fields(edit, computed_id), before=before, applied=True
                )
            )
            continue

        if edit.action == "create" and before is not None:
            applied.append(_rejected(edit, computed_id, "entry already exists"))
            continue
        if edit.action == "update" and before is None:
            applied.append(_rejected(edit, computed_id, "entry not found"))
            continue

        after = HarnessEntry(
            id=computed_id,
            kind=edit.kind,
            title=edit.title or (before.title if before else computed_id),
            content=edit.content or (before.content if before else ""),
            scope=before.scope if before else scope,
            path=edit.path or (before.path if before else "general"),
            reference=edit.reference
            if edit.reference is not None
            else (before.reference if before else {}),
            arguments=edit.arguments
            if edit.arguments is not None
            else (before.arguments if before else {}),
            metadata=edit.metadata
            if edit.metadata is not None
            else (before.metadata if before else {}),
            source="refine",
            created_at=before.created_at if before else _now(),
            updated_at=_now(),
            version=(before.version + 1) if before else 1,
        )
        records[computed_id] = after
        modified_keys.add(key)
        applied.append(
            AppliedRefinementEdit(
                **_base_fields(edit, computed_id),
                before=before,
                after=_clone(after),
                applied=True,
            )
        )

    changes = [f"{e.action} {e.kind}:{e.id}" for e in applied if e.applied]
    state.refinements.append(
        HarnessRefinementEvent(
            id=options["id"],
            trigger=proposal.summary,
            changes=changes,
            evidence=proposal.evidence,
            outcome=proposal.expected_outcome,
            created_at=_now(),
            grounded=proposal.grounded,
            detail=[asdict(e) for e in applied],
        )
    )

    return RefinementResult(
        id=options["id"],
        summary=proposal.summary,
        rationale=proposal.rationale,
        expected_outcome=proposal.expected_outcome,
        applied_edits=applied,
        harness_state_path="",
        rollback_of=options.get("rollback_of"),
        scope=scope,
        grounded=proposal.grounded,
    )


def rollback_proposal(target: RefinementResult) -> RefinementProposal:
    """Build the inverse proposal that undoes a prior refinement."""
    edits: list[RefinementEdit] = []
    for edit in reversed(target.applied_edits):
        if not edit.applied or (edit.after is None and edit.before is None):
            continue
        if edit.before is None:
            # Was a create -> revert by deleting.
            edits.append(RefinementEdit(action="delete", kind=edit.kind, id=edit.id))
        else:
            # Was an update (or create-over-existing) -> restore prior fields.
            edits.append(
                RefinementEdit(
                    action="update",
                    kind=edit.kind,
                    id=edit.id,
                    title=edit.before.title,
                    content=edit.before.content,
                    path=edit.before.path,
                    reference=edit.before.reference,
                    arguments=edit.before.arguments,
                    metadata=edit.before.metadata,
                    reason=f"Rollback {target.id}",
                )
            )
    return RefinementProposal(
        summary=f"rollback {target.id}",
        rationale=f"Revert refinement {target.id}",
        expected_outcome="prior harness state restored",
        edits=edits,
    )


def _base_fields(edit: RefinementEdit, computed_id: str) -> dict[str, Any]:
    return {
        "action": edit.action,
        "kind": edit.kind,
        "id": computed_id,
        "title": edit.title,
        "content": edit.content,
        "path": edit.path,
        "reference": edit.reference,
        "arguments": edit.arguments,
        "metadata": edit.metadata,
        "reason": edit.reason,
    }


def _rejected(edit: RefinementEdit, computed_id: str, error: str) -> AppliedRefinementEdit:
    return AppliedRefinementEdit(**_base_fields(edit, computed_id), applied=False, error=error)


def _validate_edit(edit: RefinementEdit, computed_id: str) -> str | None:
    if edit.action not in ("create", "update", "delete"):
        return f"unsupported action {edit.action!r}"
    if edit.kind not in ("prompt", "memory", "skill", "subagent"):
        return f"unsupported kind {edit.kind!r}"
    if (
        edit.kind == "prompt" or computed_id == _IMMUTABLE_BASE_ID
    ) and computed_id == _IMMUTABLE_BASE_ID:
        return "base system prompt is not editable"
    if edit.action != "create" and not edit.id:
        return f"{edit.action} requires id"
    if edit.action != "delete" and (not edit.title or not edit.content):
        return f"{edit.action} requires title and content"
    if edit.action != "delete" and edit.kind == "skill":
        if edit.arguments is None:
            return "skill create/update requires arguments"
        ref = edit.reference
        if not ref:
            return "skill create/update requires reference"
        if ref.get("type") != "python":
            return "skill reference.type must be python"
        has_import = bool(ref.get("import") or ref.get("python_import"))
        has_callable = bool(ref.get("callable") or ref.get("call_pattern"))
        if not has_import:
            return "skill reference requires python import"
        if not has_callable:
            return "skill reference requires callable or call_pattern"
    return None


# -- controller / persistence ------------------------------------------------


class HarnessController:
    """Owns a harness state file and provides apply/rollback/prompt access."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = path
        self.state = load_harness_state(str(path))

    def apply(
        self,
        proposal: RefinementProposal,
        *,
        scope: HarnessScope = "local",
        rollback_of: str | None = None,
    ) -> RefinementResult:
        result = apply_refinement_proposal(
            self.state,
            proposal,
            options={"id": new_id("ref"), "scope": scope, "rollback_of": rollback_of},
        )
        if any(e.applied for e in result.applied_edits):
            result.harness_state_path = str(self.path)
            self._save()
        return result

    def rollback(self, target: RefinementResult) -> RefinementResult:
        inverse = rollback_proposal(target)
        return self.apply(inverse, scope=target.scope or "local", rollback_of=target.id)

    def _save(self) -> None:
        save_harness_state(str(self.path), self.state)

    def format_for_prompt(
        self,
        *,
        max_entries_per_kind: int = _DEFAULT_OVERVIEW_LIMIT,
        max_refinements: int = _DEFAULT_REFINEMENT_LIMIT,
        max_content: int = _DEFAULT_CONTENT_LIMIT,
    ) -> str:
        return format_harness_state_for_prompt(
            self.state,
            max_entries_per_kind=max_entries_per_kind,
            max_refinements=max_refinements,
            max_content_length=max_content,
        )


def empty_harness_state() -> HarnessState:
    return HarnessState(
        schema=HARNESS_SCHEMA,
        entries={k: {} for k in ("prompt", "memory", "skill", "subagent")},
        refinements=[],
    )


def load_harness_state(path: str) -> HarnessState:
    """Load harness state, degrading to empty on any corruption.

    Runs before each refinement and when building the system prompt, so a
    broken file must never crash the session -- the next save rewrites it
    cleanly. (Same discipline as prime-agent's loadHarnessState.)
    """
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return empty_harness_state()
    if not isinstance(raw, dict):
        return empty_harness_state()

    state = empty_harness_state()
    state.schema = raw.get("schema", HARNESS_SCHEMA)
    for kind in state.entries:
        records = raw.get("entries", {}).get(kind)
        if not isinstance(records, dict):
            continue
        for eid, raw_entry in records.items():
            if not isinstance(raw_entry, dict):
                continue
            try:
                entry = HarnessEntry(
                    id=raw_entry.get("id", eid) or eid,
                    kind=raw_entry.get("kind", kind),
                    title=raw_entry.get("title", eid) or eid,
                    content=raw_entry.get("content", ""),
                    scope=_coerce_scope(raw_entry.get("scope")),
                    path=raw_entry.get("path", "general"),
                    reference=raw_entry.get("reference") or {},
                    arguments=raw_entry.get("arguments") or {},
                    metadata=raw_entry.get("metadata") or {},
                    source=raw_entry.get("source", "refine"),
                    created_at=raw_entry.get("created_at", ""),
                    updated_at=raw_entry.get("updated_at", ""),
                    version=int(raw_entry.get("version", 1)),
                )
            except (TypeError, ValueError):
                continue
            state.entries[kind][eid] = entry
    if isinstance(raw.get("refinements"), list):
        for ev in raw["refinements"]:
            if isinstance(ev, dict) and "id" in ev and "changes" in ev:
                state.refinements.append(
                    HarnessRefinementEvent(
                        id=ev["id"],
                        trigger=ev.get("trigger", ""),
                        changes=list(ev.get("changes", [])),
                        evidence=ev.get("evidence", ""),
                        outcome=ev.get("outcome", ""),
                        created_at=ev.get("created_at", ""),
                        grounded=bool(ev.get("grounded", False)),
                        detail=list(ev.get("detail", [])),
                    )
                )
    return state


def save_harness_state(path: str, state: HarnessState) -> None:
    """Atomic write: temp file + rename, preserving mode of any prior file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    mode = 0o600
    if os.path.exists(path):
        try:
            mode = os.stat(path).st_mode & 0o777
        except OSError:
            mode = 0o600
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(state), fh, indent=2)
            fh.write("\n")
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            with contextlib.suppress(OSError):
                os.unlink(tmp)


def _coerce_scope(value: Any) -> HarnessScope:
    return "global" if value == "global" else "local"


def format_harness_state_for_prompt(
    state: HarnessState,
    *,
    max_entries_per_kind: int = _DEFAULT_OVERVIEW_LIMIT,
    max_refinements: int = _DEFAULT_REFINEMENT_LIMIT,
    max_content_length: int = _DEFAULT_CONTENT_LIMIT,
) -> str:
    """Compact, injection-ready rendering of the harness as supplemental context.

    The base system prompt is immutable; these entries are routing/context
    hints the model may use when relevant. Mirrors prime-agent's
    formatHarnessStateForPrompt header guidance.
    """
    lines = [
        "# Continual Harness State",
        "",
        "The base system prompt is immutable. The entries below are supplemental "
        "context hints -- use them when relevant, do not treat them as rules "
        "unless they directly apply. (local) entries belong to this session; "
        "(global) entries persist across sessions.",
        "",
    ]

    total = 0
    for kind in ("prompt", "memory", "skill", "subagent"):
        entries = list(state.entries[kind].values())
        total += len(entries)
        lines.append(f"{kind}: {len(entries)}")
        for entry in entries[:max_entries_per_kind]:
            ref = ""
            if entry.kind == "skill" and entry.reference:
                ref = f" ref={json.dumps(entry.reference)[:max_content_length]}"
            args = ""
            if entry.kind == "skill" and entry.arguments:
                args = f" args={json.dumps(entry.arguments)[:max_content_length]}"
            content = entry.content.replace("\n", " ").strip()[:max_content_length]
            lines.append(
                f"- [{entry.scope}:{entry.id}] {entry.title} "
                f"(v{entry.version}){ref}{args}: {content}"
            )
        overflow = len(entries) - min(len(entries), max_entries_per_kind)
        if overflow > 0:
            lines.append(f"- +{overflow} more {kind} entries")

    if total == 0:
        lines.append("No saved harness entries yet.")

    lines.append("")
    lines.append(f"recent refinements: {len(state.refinements)}")
    for ev in state.refinements[-max_refinements:]:
        changes = ", ".join(ev.changes) if ev.changes else "no applied edits"
        tag = " [grounded]" if ev.grounded else ""
        outcome = f"; outcome: {ev.outcome[:max_content_length]}" if ev.outcome else ""
        lines.append(f"- [{ev.id}]{tag} {ev.trigger}: {changes}{outcome}")

    return "\n".join(lines).strip()
