"""The automatic model selector: pool -> catalog -> benchmarks -> shield.

Public surface (everything else is an internal module):

* :class:`SelectorProvider` — the selector as a drop-in ``LLMProvider``
  answering ``model="auto"`` / ``"auto:<category>"`` / literal ids,
* :class:`KeyPool`, :func:`discover_keys` — the API-key pool layer,
* :class:`ModelCatalog`, :func:`refresh_catalog` — live model discovery,
* :class:`BenchmarkTable` — capability scoring with provenance,
* :class:`TaskRouter`, :class:`RouterConfig`, :func:`classify` — ranking,
* :class:`RateLimitShield`, :class:`ShieldConfig` — failure absorption,
* :class:`Learner` — per (key, model) evidence that outlives restarts.
"""

from __future__ import annotations

from .benchmarks import BenchmarkTable, load_overrides, seed_summary
from .catalog import ModelCatalog, refresh_catalog
from .keys import KeyPool, discover_keys
from .learning import Learner
from .provider import SelectorProvider, decision_summary
from .router import RouterConfig, TaskProfile, TaskRouter, classify
from .shield import RateLimitShield, ShieldConfig, ShieldResult
from .types import AttemptReport, Candidate, Category, Decision, KeyState, ModelInfo

__all__ = [
    "AttemptReport",
    "BenchmarkTable",
    "Candidate",
    "Category",
    "Decision",
    "KeyPool",
    "KeyState",
    "Learner",
    "ModelCatalog",
    "ModelInfo",
    "RateLimitShield",
    "RouterConfig",
    "SelectorProvider",
    "ShieldConfig",
    "ShieldResult",
    "TaskProfile",
    "TaskRouter",
    "classify",
    "decision_summary",
    "discover_keys",
    "load_overrides",
    "refresh_catalog",
    "seed_summary",
]
