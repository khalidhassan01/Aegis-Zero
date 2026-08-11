"""Tests for P5: per-model context windows (audit #13)."""

from __future__ import annotations

from aegis_zero.core.config import ModelSettings
from aegis_zero.core.models import Message
from aegis_zero.orchestrator.context import ContextBuilder


def test_known_model_uses_its_window():
    m = ModelSettings()
    assert m.context_window("qwen2.5:7b") == 32_768
    # prompt budget reserves room for generation
    assert m.prompt_budget("qwen2.5:7b") == 32_768 - 4_096


def test_unknown_model_falls_back_to_default():
    m = ModelSettings()
    assert m.context_window("mystery-model") == m.default_context_window
    assert m.prompt_budget("mystery-model") == m.default_context_window - 4_096


def test_tiny_window_never_yields_negative_budget():
    m = ModelSettings(
        context_windows={"tiny": 1_000}, default_context_window=1_000, generation_reserve=4_096
    )
    # prompt budget must stay >= the 512 floor even when window < reserve
    assert m.prompt_budget("tiny") == 512


def test_context_windows_survive_yaml_and_env():
    from aegis_zero.core.config import load_settings

    s = load_settings(
        env={"AEGIS_MODELS__CONTEXT_WINDOWS": '{"big": 128000}', "AEGIS_MODELS__DEEP": "big"}
    )
    assert s.models.context_window("big") == 128000
    assert s.models.prompt_budget("big") == 128000 - 4_096


def test_context_builder_uses_per_model_budget():
    big = ContextBuilder(prompt_budget_for=lambda model: 32_768 if model == "big" else 2_000)
    assert big.budget_for("big") == 32_768
    assert big.budget_for("small") == 2_000


def test_context_builder_static_fallback_without_resolver():
    cb = ContextBuilder(max_tokens=5_000)
    assert cb.budget_for("anything") == 5_000


async def test_build_uses_model_specific_budget():
    # A large history must be trimmed to the per-model budget passed to
    # build(), not the static default.
    def budget_for(model: str) -> int:
        return 200 if model == "small" else 50_000

    cb = ContextBuilder(max_tokens=50_000, prompt_budget_for=budget_for)
    history = [Message(role="user", content="x" * 4_000) for _ in range(10)]
    packet = await cb.build("g", history, system="sys", model="small")
    # per-model budget (200) must not be overrun by the large history
    assert packet.tokens <= 200, f"per-model budget overrun: {packet.tokens}"
