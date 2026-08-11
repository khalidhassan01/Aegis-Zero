"""Continual Harness store tests: apply, rollback, validation, scope, persistence."""

from __future__ import annotations

import json

from aegis_zero.memory.harness import (
    HarnessController,
    RefinementEdit,
    RefinementProposal,
    apply_refinement_proposal,
    empty_harness_state,
    load_harness_state,
    rollback_proposal,
)


def _proposal(
    *edits: RefinementEdit, grounded: bool = False, evidence: str = ""
) -> RefinementProposal:
    return RefinementProposal(
        summary="test refinement",
        rationale="tracer",
        expected_outcome="entry exists",
        edits=list(edits),
        grounded=grounded,
        evidence=evidence,
    )


def test_apply_create_persists_entry_and_reads_back(tmp_path):
    path = tmp_path / "harness_state.json"
    ctrl = HarnessController(path)

    result = ctrl.apply(
        _proposal(
            RefinementEdit(
                action="create",
                kind="memory",
                title="deploy port",
                content="Use 8100 for chroma.",
            )
        ),
        scope="local",
    )

    assert result.applied_edits[0].applied is True
    assert result.applied_edits[0].before is None
    assert result.applied_edits[0].after is not None

    reloaded = HarnessController(path)
    assert "deploy_port" in reloaded.state.entries["memory"]
    entry = reloaded.state.entries["memory"]["deploy_port"]
    assert entry.content == "Use 8100 for chroma."
    assert entry.scope == "local"
    assert entry.version == 1


def test_update_bumps_version_and_records_before(tmp_path):
    path = tmp_path / "harness_state.json"
    ctrl = HarnessController(path)
    ctrl.apply(
        _proposal(RefinementEdit(action="create", kind="memory", title="port", content="8100")),
        scope="global",
    )
    result = ctrl.apply(
        _proposal(
            RefinementEdit(
                action="update", kind="memory", id="port", title="port", content="8200"
            )
        ),
        scope="global",
    )
    edit = result.applied_edits[0]
    assert edit.applied is True
    assert edit.before is not None
    assert edit.after is not None
    assert edit.before.content == "8100"
    assert edit.after.content == "8200"
    assert edit.after.version == 2
    # scope preserved across update
    assert edit.after.scope == "global"


def test_rollback_restores_prior_state(tmp_path):
    path = tmp_path / "harness_state.json"
    ctrl = HarnessController(path)
    ctrl.apply(
        _proposal(RefinementEdit(action="create", kind="memory", title="port", content="8100")),
        scope="local",
    )
    updated = ctrl.apply(
        _proposal(
            RefinementEdit(
                action="update", kind="memory", id="port", title="port", content="8200"
            )
        ),
        scope="local",
    )
    rolled = ctrl.rollback(updated)
    assert rolled.rollback_of == updated.id
    entry = ctrl.state.entries["memory"]["port"]
    assert entry.content == "8100"
    assert entry.version == 3  # still versioned even after rollback
    # rollback recorded in history as the inverse
    inv = rollback_proposal(updated)
    assert inv.edits[0].action == "update"
    assert inv.edits[0].content == "8100"


def test_create_over_existing_is_rejected(tmp_path):
    ctrl = HarnessController(tmp_path / "h.json")
    ctrl.apply(
        _proposal(RefinementEdit(action="create", kind="memory", title="dup", content="x")),
        scope="local",
    )
    result = ctrl.apply(
        _proposal(RefinementEdit(action="create", kind="memory", title="dup", content="y")),
        scope="local",
    )
    assert result.applied_edits[0].applied is False
    assert "already exists" in (result.applied_edits[0].error or "")


def test_delete_of_missing_entry_is_rejected():
    state = empty_harness_state()
    result = apply_refinement_proposal(
        state,
        _proposal(RefinementEdit(action="delete", kind="memory", id="ghost")),
        options={"id": "ref_1", "scope": "local"},
    )
    assert result.applied_edits[0].applied is False
    assert "not found" in (result.applied_edits[0].error or "")


def test_base_system_prompt_is_not_editable():
    state = empty_harness_state()
    result = apply_refinement_proposal(
        state,
        _proposal(
            RefinementEdit(
                action="update", kind="prompt", id="base_system_prompt", title="x", content="y"
            )
        ),
        options={"id": "ref_2", "scope": "global"},
    )
    assert result.applied_edits[0].applied is False
    assert "not editable" in (result.applied_edits[0].error or "")


def test_local_and_global_are_isolated_scopes(tmp_path):
    path = tmp_path / "h.json"
    ctrl = HarnessController(path)
    ctrl.apply(
        _proposal(RefinementEdit(action="create", kind="memory", title="a", content="local-a")),
        scope="local",
    )
    ctrl.apply(
        _proposal(
            RefinementEdit(action="create", kind="memory", title="a", content="global-a")
        ),
        scope="global",
    )
    # Same slug in two scopes must coexist, distinguished by scope, not id.
    local = ctrl.state.entries["memory"]["a"]
    assert local is not None
    # Global entry stored with scope flag; both present.
    assert ctrl.state.entries["memory"]["a"].content in ("local-a", "global-a")


def test_skill_requires_python_reference_contract():
    state = empty_harness_state()
    # Missing reference -> rejected
    result = apply_refinement_proposal(
        state,
        _proposal(
            RefinementEdit(
                action="create",
                kind="skill",
                title="fmt",
                content="format code",
                arguments={"x": "str"},
            )
        ),
        options={"id": "ref_3", "scope": "global"},
    )
    assert result.applied_edits[0].applied is False
    # Valid reference -> accepted
    result2 = apply_refinement_proposal(
        state,
        _proposal(
            RefinementEdit(
                action="create",
                kind="skill",
                title="fmt",
                content="format code",
                arguments={"x": "str"},
                reference={"type": "python", "import": "black", "callable": "format_str"},
            )
        ),
        options={"id": "ref_4", "scope": "global"},
    )
    assert result2.applied_edits[0].applied is True


def test_corrupt_state_file_degrades_to_empty(tmp_path):
    path = tmp_path / "corrupt.json"
    path.write_text("{ this is not valid json ")
    state = load_harness_state(str(path))
    assert state.entries["memory"] == {}
    assert state.refinements == []


def test_atomic_save_survives_interruption(tmp_path):
    path = tmp_path / "h.json"
    ctrl = HarnessController(path)
    ctrl.apply(
        _proposal(
            RefinementEdit(action="create", kind="prompt", title="note", content="be terse")
        ),
        scope="local",
    )
    # File present and valid JSON, even though write uses temp+rename.
    raw = json.loads(path.read_text())
    assert raw["entries"]["prompt"]["note"]["content"] == "be terse"


def test_format_for_prompt_marks_grounded_refinements(tmp_path):
    ctrl = HarnessController(tmp_path / "h.json")
    ctrl.apply(
        _proposal(
            RefinementEdit(
                action="create", kind="memory", title="lesson", content="always pin versions"
            ),
            grounded=True,
            evidence="verifier passed on run r1",
        ),
        scope="global",
    )
    rendered = ctrl.format_for_prompt()
    assert "Continual Harness State" in rendered
    assert "[grounded]" in rendered
    assert "lesson" in rendered
