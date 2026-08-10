from __future__ import annotations

import pytest

from aegis_zero.core.config import load_settings
from aegis_zero.core.errors import ConfigError


def test_defaults_are_sane():
    s = load_settings(env={})
    assert s.provider.kind == "openai"
    assert s.memory.backend == "memory"
    assert s.max_steps > 0


def test_env_overrides_nested_sections():
    s = load_settings(
        env={
            "AEGIS_PROVIDER__BASE_URL": "http://example:9000/v1",
            "AEGIS_PROVIDER__TIMEOUT": "42.5",
            "AEGIS_MODELS__FAST": "tiny",
            "AEGIS_MAX_STEPS": "7",
        }
    )
    assert s.provider.base_url == "http://example:9000/v1"
    assert s.provider.timeout == 42.5
    assert s.models.fast == "tiny"
    assert s.max_steps == 7


def test_env_parses_tuples_and_bools():
    s = load_settings(
        env={
            "AEGIS_POLICY__DENIED_TOOLS": "shell, write_file",
            "AEGIS_POLICY__ALLOW_NETWORK": "false",
        }
    )
    assert s.policy.denied_tools == ("shell", "write_file")
    assert s.policy.allow_network is False


def test_unknown_key_is_rejected():
    with pytest.raises(ConfigError):
        load_settings(env={"AEGIS_NOPE": "1"})


def test_missing_file_is_rejected():
    with pytest.raises(ConfigError):
        load_settings("/nonexistent/aegis.yaml", env={})


def test_yaml_file_is_layered_under_env(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("max_steps: 3\nmodels:\n  fast: from-file\n")
    s = load_settings(p, env={"AEGIS_MODELS__FAST": "from-env"})
    assert s.max_steps == 3
    assert s.models.fast == "from-env"
