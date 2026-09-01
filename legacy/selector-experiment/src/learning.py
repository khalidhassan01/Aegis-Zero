"""Learning layer: per (key, model) performance, persisted as evidence.

Every shielded attempt feeds an exponentially-weighted moving average of
success rate and latency for the (key fingerprint, model) pair that
served it. The state file stores fingerprints only — never a secret —
so it is safe to inspect, back up, or sync.

Selection consults this evidence in two ways:

* reliability weight: a pair that fails often is demoted long before it
  is exhausted from the candidate ladder,
* latency weight: for latency-sensitive categories (chat) a proven-fast
  pair outranks a nominally-better model with slow service.

A new key starts with a neutral prior and converges after a handful of
requests — that is the "grows and learns with every new key" promise,
with numbers instead of adjectives.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .types import AttemptReport

#: How strongly new evidence replaces old (higher = shorter memory).
_EWMA_ALPHA = 0.3
#: Latency clamp so one pathological outlier cannot poison the average.
_LATENCY_CLAMP_MS = 60_000.0


@dataclass(slots=True)
class PairStats:
    """Rolling evidence for one (key fingerprint, model) pair."""

    success_ewma: float = 1.0  # starts optimistic; failures demote fast
    latency_ewma_ms: float = 2_000.0
    samples: int = 0
    last_seen: float = 0.0

    def update(self, ok: bool, latency_ms: float, at: float) -> None:
        latency = min(max(latency_ms, 1.0), _LATENCY_CLAMP_MS)
        self.success_ewma += _EWMA_ALPHA * ((1.0 if ok else 0.0) - self.success_ewma)
        self.latency_ewma_ms += _EWMA_ALPHA * (latency - self.latency_ewma_ms)
        self.samples += 1
        self.last_seen = at

    @property
    def reliability(self) -> float:
        """0..1 with sample-size damping: trust grows with evidence."""
        trust = min(self.samples / 10.0, 1.0)
        return self.success_ewma * (0.5 + 0.5 * trust) + 0.5 * (1.0 - trust)


class Learner:
    """Accumulates and persists pair evidence; consults it for weights."""

    def __init__(self, state_path: str | Path | None = None) -> None:
        self.state_path = Path(state_path).expanduser() if state_path else None
        self._pairs: dict[str, PairStats] = {}
        self._dirty = False
        self._load()

    # -- keying -------------------------------------------------------------

    @staticmethod
    def pair_key(fingerprint: str, model_id: str) -> str:
        return f"{fingerprint}/{model_id}"

    # -- evidence -----------------------------------------------------------

    def record(self, report: AttemptReport) -> None:
        """Fold one attempt into the evidence base."""
        key = self.pair_key(report.key_fingerprint, report.model)
        stats = self._pairs.setdefault(key, PairStats())
        stats.update(
            ok=report.outcome == "success",
            latency_ms=report.latency_ms,
            at=report.at or time.time(),
        )
        self._dirty = True

    def reliability(self, fingerprint: str, model_id: str) -> float:
        """0..1 reliability weight (damped toward 1.0 with no evidence)."""
        stats = self._pairs.get(self.pair_key(fingerprint, model_id))
        return stats.reliability if stats else 1.0

    def latency(self, fingerprint: str, model_id: str) -> float:
        """Expected latency in ms (prior 2s with no evidence)."""
        stats = self._pairs.get(self.pair_key(fingerprint, model_id))
        return stats.latency_ewma_ms if stats else 2_000.0

    def samples(self, fingerprint: str, model_id: str) -> int:
        stats = self._pairs.get(self.pair_key(fingerprint, model_id))
        return stats.samples if stats else 0

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        if not self.state_path or not self.state_path.is_file():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            for key, row in (data.get("pairs") or {}).items():
                self._pairs[key] = PairStats(
                    success_ewma=float(row.get("success_ewma", 1.0)),
                    latency_ewma_ms=float(row.get("latency_ewma_ms", 2_000.0)),
                    samples=int(row.get("samples", 0)),
                    last_seen=float(row.get("last_seen", 0.0)),
                )
        except (ValueError, OSError):
            # Corrupted state is regrettable but must not take routing
            # down: start from a blank, evidence-backed-again base.
            self._pairs = {}

    def save(self) -> None:
        """Persist atomically. No-op when nothing changed or no path set."""
        if not self.state_path or not self._dirty:
            return
        payload: dict[str, Any] = {
            "saved_at": time.time(),
            "pairs": {k: asdict(v) for k, v in self._pairs.items()},
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)
        self._dirty = False

    # -- reporting ----------------------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        """Evidence table for status output (fingerprints only)."""
        rows = []
        for key, stats in sorted(self._pairs.items(), key=lambda kv: -kv[1].samples):
            fingerprint, _, model = key.partition("/")
            rows.append(
                {
                    "key": fingerprint,
                    "model": model,
                    "samples": stats.samples,
                    "success_ewma": round(stats.success_ewma, 3),
                    "reliability": round(stats.reliability, 3),
                    "latency_ewma_ms": round(stats.latency_ewma_ms, 0),
                }
            )
        return rows

    def forget(self, fingerprint: str, model_id: str) -> bool:
        key = self.pair_key(fingerprint, model_id)
        if key in self._pairs:
            del self._pairs[key]
            self._dirty = True
            return True
        return False
