"""CLI tests for `aegis harness inspect` / `aegis harness rollback`."""

from __future__ import annotations

import asyncio

from aegis_zero.cli import build_parser
from aegis_zero.memory.harness import HarnessController, RefinementEdit, RefinementProposal


def _seed(path):
    ctrl = HarnessController(path)
    res = ctrl.apply(
        RefinementProposal(
            summary="add lesson",
            rationale="verified run",
            expected_outcome="reuse",
            edits=[
                RefinementEdit(action="create", kind="memory", title="port", content="8100")
            ],
        ),
        scope="global",
    )
    return ctrl, res


def test_harness_inspect_lists_entries_and_history(tmp_path, capsys):
    path = tmp_path / "harness_state.json"
    _seed(path)

    args = build_parser().parse_args(["harness", "inspect", "--path", str(path)])
    rc = asyncio.run(args.fn(args))
    assert rc == 0
    out = capsys.readouterr().out
    assert "port" in out
    assert "8100" in out
    assert "add lesson" in out  # refinement history


def test_harness_rollback_reverts_last_refinement(tmp_path, capsys):
    path = tmp_path / "harness_state.json"
    _, res = _seed(path)

    args = build_parser().parse_args(
        ["harness", "rollback", "--path", str(path), "--refinement", res.id]
    )
    rc = asyncio.run(args.fn(args))
    assert rc == 0
    out = capsys.readouterr().out
    assert "rolled back" in out.lower()

    reloaded = HarnessController(path)
    assert "port" not in reloaded.state.entries["memory"], "entry should be gone after rollback"


def test_harness_rollback_unknown_id_is_error(tmp_path, capsys):
    path = tmp_path / "harness_state.json"
    _seed(path)
    args = build_parser().parse_args(
        ["harness", "rollback", "--path", str(path), "--refinement", "ref_does_not_exist"]
    )
    rc = asyncio.run(args.fn(args))
    assert rc == 1
