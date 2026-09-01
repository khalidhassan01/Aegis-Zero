"""Benchmark-based capability scoring: model x category -> 0..100.

Two sources feed a score, in order of precedence:

1. a user override file (``benchmarks.yaml``) — exact id or prefix match,
2. the curated seed table below,
3. a neutral prior with signal nudges for models nobody has tabulated yet.

The seed table is distilled from public evaluation standings as of
2026-08 (LMArena Elo, SWE-bench Verified, LiveCodeBench, AIME, GPQA,
MMMU/MME for vision, plus measured serving speed per model family). It is
a *prior*, not gospel: the learning layer (``learning.py``) corrects it
with live per-key evidence, and ``Category.LONG_CONTEXT`` is computed
from live context metadata rather than frozen at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .types import Category, ModelInfo

SEED_VERSION = "2026-08-31.1"

#: Category axes a seed row may carry.
_AXES = ("chat", "reasoning", "code", "vision", "safety")

#: Curated scores for the free-model corpus (0-100 per axis). A missing
#: axis means "not applicable" (rendered 0.0): e.g. a text-only model has
#: no vision score, and the router's hard filter would exclude it anyway.
_SEED: dict[str, dict[str, float]] = {
    # --- frontier free tier ---
    "z-ai/glm-5.2:free": {
        "chat": 84,
        "reasoning": 92,
        "code": 90,
        "safety": 62,
    },
    "nvidia/nemotron-3-ultra-550b-a55b:free": {
        "chat": 68,
        "reasoning": 94,
        "code": 88,
        "safety": 64,
    },
    "nvidia/nemotron-3-super-120b-a12b:free": {
        "chat": 80,
        "reasoning": 88,
        "code": 86,
        "safety": 62,
    },
    "nvidia/nemotron-3.5-lightning:free": {
        "chat": 90,
        "reasoning": 82,
        "code": 80,
        "safety": 60,
    },
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free": {
        "chat": 86,
        "reasoning": 74,
        "code": 68,
        "vision": 78,
        "safety": 70,
    },
    "nvidia/nemotron-3.5-content-safety:free": {
        "chat": 40,
        "reasoning": 40,
        "code": 30,
        "vision": 70,
        "safety": 95,
    },
    "minimax/minimax-m3:free": {
        "chat": 82,
        "reasoning": 90,
        "code": 87,
        "vision": 84,
        "safety": 64,
    },
    "minimax/minimax-m2.7:free": {
        "chat": 78,
        "reasoning": 84,
        "code": 80,
        "safety": 60,
    },
    # --- open-weights workhorses ---
    "google/gemma-4-31b-it:free": {
        "chat": 82,
        "reasoning": 80,
        "code": 76,
        "vision": 86,
        "safety": 66,
    },
    "google/gemma-4-26b-a4b-it:free": {
        "chat": 86,
        "reasoning": 76,
        "code": 72,
        "vision": 84,
        "safety": 64,
    },
    # --- code specialists ---
    "poolside/laguna-s-2.1:free": {
        "chat": 76,
        "reasoning": 78,
        "code": 93,
        "safety": 55,
    },
    "poolside/laguna-xs-2.1:free": {
        "chat": 84,
        "reasoning": 70,
        "code": 88,
        "safety": 52,
    },
    "cohere/north-mini-code:free": {
        "chat": 80,
        "reasoning": 68,
        "code": 84,
        "safety": 58,
    },
    # --- fast / long-context / omni ---
    "inclusionai/ling-3.0-flash-fin:free": {
        "chat": 88,
        "reasoning": 70,
        "code": 64,
        "safety": 60,
    },
    "liquid/lfm-2.5-2.6b:free": {
        "chat": 93,
        "reasoning": 52,
        "code": 50,
        "safety": 50,
    },
    "thinkingmachines/inkling:free": {
        "chat": 76,
        "reasoning": 89,
        "code": 82,
        "vision": 88,
        "safety": 64,
    },
    "thinkingmachines/inkling-small:free": {
        "chat": 86,
        "reasoning": 80,
        "code": 74,
        "vision": 86,
        "safety": 62,
    },
    "dots-studio/dots-3-note-preview:free": {
        "chat": 84,
        "reasoning": 66,
        "code": 58,
        "vision": 76,
        "safety": 58,
    },
}

#: Family prefixes for models whose exact id is not in the seed (new
#: point releases should inherit the family's standing, not the neutral
#: prior): "z-ai/glm-5.5:free" inherits glm-5.2's profile.
_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("nemotron-3-ultra", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    ("nemotron-3-super", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("nemotron-3.5-lightning", "nvidia/nemotron-3.5-lightning:free"),
    ("nemotron-3.5-content-safety", "nvidia/nemotron-3.5-content-safety:free"),
    ("nemotron", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("glm-5", "z-ai/glm-5.2:free"),
    ("glm-", "z-ai/glm-5.2:free"),
    ("minimax-m3", "minimax/minimax-m3:free"),
    ("minimax", "minimax/minimax-m2.7:free"),
    ("gemma-4", "google/gemma-4-31b-it:free"),
    ("gemma", "google/gemma-4-31b-it:free"),
    ("laguna-s", "poolside/laguna-s-2.1:free"),
    ("laguna", "poolside/laguna-xs-2.1:free"),
    ("inkling-small", "thinkingmachines/inkling-small:free"),
    ("inkling", "thinkingmachines/inkling:free"),
    ("ling-", "inclusionai/ling-3.0-flash-fin:free"),
    ("lfm-", "liquid/lfm-2.5-2.6b:free"),
)

_SMALL_MARKERS = ("nano", "mini", "small", "flash", "lite", "tiny", "2.6b", "3b", "4b", "xs")
_BIG_MARKERS = ("ultra", "pro", "max", "large", "550b", "405b")

#: Name tokens that mark an embedding model. Shared by the benchmark
#: score and the router's hard filter so the two can never disagree.
_EMBEDDING_TOKENS = ("embed", "bge", "e5", "gte", "minilm")


def is_embedding_model(model_id: str) -> bool:
    """True when the model id names an embedding model.

    The router uses this as a hard filter for embedding requests: a chat
    model pressed into embedding duty would burn the whole ladder with
    doomed calls before the configured fallback ever ran.
    """
    lowered = model_id.lower()
    return any(token in lowered for token in _EMBEDDING_TOKENS)


class BenchmarkTable:
    """Scores models per category, with explainable provenance."""

    def __init__(self, overrides: Mapping[str, Mapping[str, float]] | None = None) -> None:
        # Overrides are user-supplied per-model scores (same shape as the
        # seed). Kept separate so `explain` can report precedence honestly.
        self._overrides: dict[str, dict[str, float]] = {
            k: {a: float(v) for a, v in row.items()} for k, row in (overrides or {}).items()
        }

    # -- public API ---------------------------------------------------------

    def score(self, model: ModelInfo, category: Category) -> float:
        """The 0-100 capability score of ``model`` for ``category``."""
        return self.explain(model, category)[0]

    def explain(self, model: ModelInfo, category: Category) -> tuple[float, str]:
        """Score plus where it came from ("override" | "seed" | "family" | "prior")."""
        axis = category.value
        if category is Category.LONG_CONTEXT:
            return self._long_context(model), self._lc_source(model)
        if category is Category.EMBEDDING:
            return self._embedding(model)

        for source, table in (("override", self._overrides), ("seed", _SEED)):
            row = self._lookup(table, model.id)
            if row is not None:
                return float(row.get(axis, 0.0)), source
        family = self._family_match(model.id)
        if family is not None:
            row = _SEED[family]
            return float(row.get(axis, 0.0)), "family"
        return self._prior(model, category), "prior"

    def top(self, model: ModelInfo) -> dict[str, float]:
        """All category scores for one model (status display)."""
        out: dict[str, float] = {}
        for cat in (Category.CHAT, Category.REASONING, Category.CODE, Category.VISION):
            out[cat.value] = round(self.score(model, cat), 1)
        return out

    # -- internals ----------------------------------------------------------

    def _lookup(
        self, table: Mapping[str, Mapping[str, float]], model_id: str
    ) -> Mapping[str, float] | None:
        """Exact match, then longest prefix match inside one table."""
        if model_id in table:
            return table[model_id]
        # ":free" and similar suffixes must not break an override entry
        # written for the paid id (or vice versa).
        base = model_id.split(":")[0]
        best: Mapping[str, float] | None = None
        best_len = -1
        for key in table:
            key_base = key.split(":")[0]
            if base.startswith(key_base) and len(key_base) > best_len:
                best, best_len = table[key], len(key_base)
        return best

    def _family_match(self, model_id: str) -> str | None:
        lowered = model_id.lower()
        for prefix, canonical in _FAMILY_PREFIXES:
            if prefix in lowered:
                return canonical
        return None

    def _prior(self, model: ModelInfo, category: Category) -> float:
        """Neutral prior adjusted by cheap, honest signals."""
        s = 60.0
        lowered = model.id.lower()
        small = any(m in lowered for m in _SMALL_MARKERS)
        big = any(m in lowered for m in _BIG_MARKERS)
        if category is Category.CHAT:
            if small:
                s += 10.0
            if big:
                s -= 6.0
        elif category in (Category.REASONING, Category.CODE):
            if small:
                s -= 10.0
            if big:
                s += 8.0
            if model.supports_tools and category is Category.CODE:
                s += 8.0
        elif category is Category.VISION:
            s = 55.0 if model.supports_vision else 0.0
        elif category is Category.SAFETY:
            s = 60.0
        return min(max(s, 0.0), 100.0)

    def _long_context(self, model: ModelInfo) -> float:
        """Long-context quality is live metadata, not a frozen number:
        reasoning strength weighted by how much window the model actually
        has, so a 1M-context reasoner outranks a 128k one."""
        reasoning = self.score(model, Category.REASONING)
        ctx = model.context_length
        ctx_factor = min(ctx / 1_048_576, 1.0)  # 1M window is full marks
        return round(0.65 * reasoning + 35.0 * ctx_factor, 1)

    def _lc_source(self, model: ModelInfo) -> str:
        base = self.explain(model, Category.REASONING)[1]
        return f"{base}+ctx"

    def _embedding(self, model: ModelInfo) -> tuple[float, str]:
        if is_embedding_model(model.id):
            return 80.0, "prior"
        return 0.0, "prior"


def load_overrides(path: str | Path | None) -> dict[str, dict[str, float]]:
    """Read a user benchmark override file (same shape as the seed).

    Any structure it has is trusted as-is; a broken file is a config
    error, not a silent fall-back to curated values.
    """
    if not path:
        return {}
    p = Path(path).expanduser()
    if not p.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"invalid benchmarks file {p}: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(f"benchmarks file {p} must be a mapping")
    out: dict[str, dict[str, float]] = {}
    for model_id, row in loaded.items():
        if isinstance(row, Mapping):
            out[str(model_id)] = {str(k): float(v) for k, v in row.items() if k in _AXES}
    return out


def seed_summary() -> dict[str, Any]:
    """Provenance card for status output: what the seed claims to know."""
    return {
        "seed_version": SEED_VERSION,
        "seed_models": len(_SEED),
        "sources": [
            "LMArena Elo (chat/overall)",
            "SWE-bench Verified + LiveCodeBench (code)",
            "AIME / GPQA / MMLU-Pro (reasoning)",
            "MMMU / MME (vision)",
            "provider-published serving speed (chat latency prior)",
        ],
    }
