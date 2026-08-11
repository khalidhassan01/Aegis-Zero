"""Reliability reporting (P4 / τ-bench, arXiv:2406.12045).

pass@1 reports whether an agent *can* succeed; ``pass^k`` reports whether it
succeeds *k times in a row*. Agents that look strong at pass@1 collapse under
pass^k — they are unreliable rather than incapable. Running a goal ``k`` times
and reporting the consistency rate is the only honest way to claim a framework
improved, because most "improvements" are really just spending more compute.

This module is pure: it takes a sequence of outcomes and returns the metrics,
so it is trivial to test offline without any model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class ReliabilityReport:
    """Result of running a goal ``n`` times and checking it ``k`` more.

    Attributes:
        n: number of runs executed.
        k: the streak length used for the pass^k metric.
        passes: number of runs that succeeded (``ok``).
        pass_at_1: ``passes / n`` — the probability a single run succeeds.
        pass_at_k: probability all of ``k`` consecutive runs succeed,
            estimated as ``pass_at_1 ** k`` under the (stated) assumption of
            independent runs. This is a Wilson-free point estimate; for small
            n the confidence interval below is the honest qualifier.
        lower: lower bound of the 95% Wilson score interval for pass^k.
        upper: upper bound of the same interval.
        mean_tokens: mean prompt+completion tokens per run.
        mean_seconds: mean wall-clock seconds per run.
        mean_revisions: mean revision count per run.
    """

    n: int
    k: int
    passes: int
    pass_at_1: float
    pass_at_k: float
    lower: float
    upper: float
    mean_tokens: float
    mean_seconds: float
    mean_revisions: float

    def summary(self) -> dict[str, float]:
        return {
            "n": self.n,
            "k": self.k,
            "pass@1": round(self.pass_at_1, 4),
            f"pass@{self.k}": round(self.pass_at_k, 4),
            "pass@k_lower": round(self.lower, 4),
            "pass@k_upper": round(self.upper, 4),
            "mean_tokens": round(self.mean_tokens, 1),
            "mean_seconds": round(self.mean_seconds, 3),
            "mean_revisions": round(self.mean_revisions, 3),
        }


def _wilson_bounds(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion.

    Used so a small sample of runs does not masquerade as precision: a 3/3
    result reports a wide interval rather than a falsely exact 1.0.
    """
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def reliability_report(
    outcomes: list[bool],
    *,
    k: int = 3,
    tokens: list[float] | None = None,
    seconds: list[float] | None = None,
    revisions: list[float] | None = None,
) -> ReliabilityReport:
    """Build a :class:`ReliabilityReport` from raw per-run measurements.

    ``outcomes`` is one bool per run (``True`` == success). The remaining
    lists, when provided, must be the same length and are averaged for the
    cost/revision diagnostics.
    """
    n = len(outcomes)
    passes = sum(1 for o in outcomes if o)
    pass_at_1 = passes / n if n else 0.0
    # Independence assumption is explicit in the report; callers that want a
    # stricter measure can compute a streak directly from `outcomes`.
    pass_at_k = pass_at_1**k

    # Wilson interval on the *per-run* success proportion, then raised to k
    # to bound the streak probability. This is conservative-ish: it bounds the
    # streak by the interval endpoints rather than the delta-method variance.
    lo, hi = _wilson_bounds(passes, n)

    def _mean(xs: list[float] | None) -> float:
        return (sum(xs) / len(xs)) if xs else 0.0

    return ReliabilityReport(
        n=n,
        k=k,
        passes=passes,
        pass_at_1=pass_at_1,
        pass_at_k=pass_at_k,
        lower=lo**k,
        upper=hi**k,
        mean_tokens=_mean(tokens),
        mean_seconds=_mean(seconds),
        mean_revisions=_mean(revisions),
    )
