"""Tests for P4: pass^k reliability reporting (τ-bench, arXiv:2406.12045)."""

from __future__ import annotations

from aegis_zero.orchestrator.reliability import reliability_report


def test_perfect_run_is_pass_k_one():
    r = reliability_report([True] * 5, k=3)
    assert r.passes == 5
    assert r.pass_at_1 == 1.0
    assert r.pass_at_k == 1.0
    # Wilson interval on a perfect sample is still bounded below 1.0 unless
    # n is enormous; for 5/5 it is strictly less than 1.0/1.0.
    assert r.lower < 1.0
    assert r.upper == 1.0


def test_partial_pass_lowers_pass_k():
    # 3 of 5 pass -> pass@1 = 0.6, pass@3 = 0.216
    r = reliability_report([True, True, True, False, False], k=3)
    assert r.pass_at_1 == 0.6
    assert abs(r.pass_at_k - 0.216) < 1e-9


def test_perfect_pass_k_interval_is_tight():
    # With many runs the lower bound on pass^k approaches 1.0 (here ~0.80 for
    # k=3 over 50/50, vs the point estimate of exactly 1.0).
    r = reliability_report([True] * 50, k=3)
    assert r.lower > 0.8


def test_cost_and_revision_means_are_averaged():
    r = reliability_report(
        [True, False],
        k=2,
        tokens=[100.0, 200.0],
        seconds=[1.0, 3.0],
        revisions=[0.0, 2.0],
    )
    assert r.mean_tokens == 150.0
    assert r.mean_seconds == 2.0
    assert r.mean_revisions == 1.0


def test_empty_run_is_safe():
    r = reliability_report([], k=3)
    assert r.n == 0
    assert r.pass_at_1 == 0.0
    assert r.pass_at_k == 0.0
    assert r.lower == 0.0 and r.upper == 0.0


async def test_engine_reliability_runs_goal_n_times():
    from aegis_zero.orchestrator import AgentEngine, EngineConfig
    from aegis_zero.orchestrator.reliability import reliability_report as _rr
    from aegis_zero.providers import EchoProvider

    verdict = '{"verdict":"pass","confidence":0.9,"issues":[]}'
    # 4 deterministic successful runs
    provider = EchoProvider(script=["answer", verdict] * 4)
    engine = AgentEngine(provider, config=EngineConfig(fast_model="f", deep_model="d"))

    # Drive the engine through Aegis.reliability-equivalent logic directly.
    results = [await engine.run("hi") for _ in range(4)]
    report = _rr(outcomes=[r.ok for r in results], k=3)
    assert report.n == 4
    assert report.passes == 4
    assert report.pass_at_1 == 1.0
