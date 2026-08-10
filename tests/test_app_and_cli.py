from __future__ import annotations

import json
from dataclasses import replace

import pytest

from aegis_zero import build_agent, load_settings
from aegis_zero.cli import build_parser, main
from aegis_zero.tools import AutoApprove


def echo_settings(**kw):
    s = load_settings(env={})
    return s.with_overrides(provider=replace(s.provider, kind="echo"), **kw)


def test_agent_assembles_from_settings():
    agent = build_agent(echo_settings(), approval=AutoApprove())
    assert agent.engine is not None
    assert agent.memory is not None
    assert "calculate" in agent.registry.names()


def test_memory_can_be_disabled():
    assert build_agent(echo_settings(), enable_memory=False).memory is None


async def test_agent_ask_end_to_end():
    async with build_agent(echo_settings(), approval=AutoApprove()) as agent:
        result = await agent.ask("hi")
        assert result.answer
        assert agent.metrics.snapshot()["runs"] == 1


async def test_policy_settings_reach_the_engine():
    s = echo_settings()
    policy = replace(s.policy, denied_tools=("write_file",))
    agent = build_agent(s.with_overrides(policy=policy))
    verdict = agent.engine.policy.decide("write_file", {"path": "/tmp/x"})
    assert verdict.decision.value == "deny"


def test_parser_requires_a_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_parser_run_defaults():
    args = build_parser().parse_args(["run", "do a thing"])
    assert args.goal == "do a thing"
    assert args.approve == "console"


def test_cli_config_command(capsys, monkeypatch):
    monkeypatch.setenv("AEGIS_MODELS__FAST", "cli-model")
    assert main(["config"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["models"]["fast"] == "cli-model"


def test_cli_tools_command(capsys, monkeypatch):
    monkeypatch.setenv("AEGIS_PROVIDER__KIND", "echo")
    assert main(["tools"]) == 0
    out = capsys.readouterr().out
    assert "calculate" in out and "risk=" in out


def test_cli_run_with_echo_provider(capsys, monkeypatch):
    monkeypatch.setenv("AEGIS_PROVIDER__KIND", "echo")
    code = main(["run", "hello there", "--approve", "auto",
                 "--no-memory", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert "answer" in payload and "run_id" in payload
    assert code in (0, 1)
