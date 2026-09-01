"""Model catalog: live discovery, disk cache, embedded seed fallback.

The catalog answers "which models exist and what can they do" from the
best source available, in this order:

1. a live fetch (OpenRouter's public ``/api/v1/models`` needs no key and
   reports pricing, context, and supported parameters per model),
2. the on-disk cache of the last successful fetch (TTL-bounded),
3. the embedded seed snapshot below (offline cold start).

Free-ness is decided by data, not by naming convention: a model is free
only when both prompt and completion prices are exactly zero. That keeps
a renamed or newly-launched ":free"-suffixed paid model from ever leaking
into the pool by accident.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import AegisError
from .keys import KeyRecord
from .types import ModelInfo

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def parse_openrouter_models(payload: dict[str, Any]) -> list[ModelInfo]:
    """Normalize an OpenRouter /models payload into ModelInfo rows."""
    out: list[ModelInfo] = []
    for raw in payload.get("data") or []:
        try:
            pricing = raw.get("pricing") or {}
            free = (
                str(pricing.get("prompt", "1")) == "0"
                and str(pricing.get("completion", "1")) == "0"
            )
            params = raw.get("supported_parameters") or []
            arch = raw.get("architecture") or {}
            modality = str(arch.get("modality") or "text->text")
            inputs, _, outputs = modality.partition("->")
            out.append(
                ModelInfo(
                    id=str(raw.get("id", "")),
                    provider="openrouter",
                    context_length=int(raw.get("context_length") or 8_192),
                    free=free,
                    supports_tools="tools" in params,
                    supports_vision="image" in inputs,
                    supports_structured_outputs="structured_outputs" in params,
                    supports_reasoning_effort="reasoning_effort" in params,
                    text_out_only="text" in outputs and "audio" not in outputs,
                    meta_router=str(raw.get("id")) in ("openrouter/free",),
                    description=str(raw.get("description") or "")[:200],
                )
            )
        except (TypeError, ValueError, AttributeError):
            continue  # one malformed record must not sink the catalog
    return out


#: Embedded snapshot of the free-model corpus, fetched live from
#: OpenRouter on 2026-08-31. Capabilities transcribed verbatim from
#: `supported_parameters` / `architecture.modality`. This is the offline
#: cold start; the first `refresh` with connectivity replaces it.
SEED_CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo(
        id="z-ai/glm-5.2:free",
        provider="openrouter",
        context_length=256_000,
        supports_tools=True,
        supports_structured_outputs=True,
        supports_reasoning_effort=True,
        description="GLM 5.2 — frontier open agentic model.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3-ultra-550b-a55b:free",
        provider="openrouter",
        context_length=1_000_000,
        supports_tools=True,
        supports_reasoning_effort=True,
        description="Nemotron 3 Ultra 550B-A55B — deep reasoning MoE.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3-super-120b-a12b:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        supports_structured_outputs=True,
        supports_reasoning_effort=True,
        description="Nemotron 3 Super 120B-A12B — balanced reasoner.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3.5-lightning:free",
        provider="openrouter",
        context_length=1_000_000,
        supports_tools=True,
        description="Nemotron 3.5 Lightning — fast 1M-context generalist.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        provider="openrouter",
        context_length=256_000,
        supports_tools=True,
        supports_vision=True,
        description="Nemotron 3 Nano Omni 30B-A3B — audio/image/video input.",
    ),
    ModelInfo(
        id="nvidia/nemotron-3.5-content-safety:free",
        provider="openrouter",
        context_length=128_000,
        supports_vision=True,
        description="Nemotron 3.5 Content Safety — moderation classifier.",
    ),
    ModelInfo(
        id="minimax/minimax-m3:free",
        provider="openrouter",
        context_length=1_048_576,
        supports_tools=True,
        supports_vision=True,
        description="MiniMax M3 — 1M-context multimodal reasoner.",
    ),
    ModelInfo(
        id="minimax/minimax-m2.7:free",
        provider="openrouter",
        context_length=196_608,
        supports_tools=True,
        description="MiniMax M2.7 — previous generation.",
    ),
    ModelInfo(
        id="google/gemma-4-31b-it:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        supports_vision=True,
        description="Gemma 4 31B IT — multimodal instruction model.",
    ),
    ModelInfo(
        id="google/gemma-4-26b-a4b-it:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        supports_vision=True,
        description="Gemma 4 26B A4B IT — fast MoG multimodal.",
    ),
    ModelInfo(
        id="poolside/laguna-s-2.1:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        description="Poolside Laguna S 2.1 — code specialist.",
    ),
    ModelInfo(
        id="poolside/laguna-xs-2.1:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        description="Poolside Laguna XS 2.1 — fast code model.",
    ),
    ModelInfo(
        id="cohere/north-mini-code:free",
        provider="openrouter",
        context_length=256_000,
        supports_tools=True,
        description="Cohere North Mini Code — compact coder.",
    ),
    ModelInfo(
        id="inclusionai/ling-3.0-flash-fin:free",
        provider="openrouter",
        context_length=262_144,
        supports_tools=True,
        description="Ling 3.0 Flash — finance-tuned fast model.",
    ),
    ModelInfo(
        id="liquid/lfm-2.5-2.6b:free",
        provider="openrouter",
        context_length=65_536,
        supports_tools=True,
        supports_structured_outputs=True,
        description="Liquid LFM 2.5 2.6B — tiny, ultra-low-latency.",
    ),
    ModelInfo(
        id="thinkingmachines/inkling:free",
        provider="openrouter",
        context_length=1_048_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning_effort=True,
        description="Inkling — 1M-context multimodal reasoner.",
    ),
    ModelInfo(
        id="thinkingmachines/inkling-small:free",
        provider="openrouter",
        context_length=1_048_576,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning_effort=True,
        description="Inkling Small — faster inkling.",
    ),
    ModelInfo(
        id="dots-studio/dots-3-note-preview:free",
        provider="openrouter",
        context_length=512_000,
        supports_tools=True,
        supports_vision=True,
        supports_structured_outputs=True,
        description="Dots 3 Note — vision preview.",
    ),
    # Excluded from routing but kept visible in the catalog:
    ModelInfo(
        id="openrouter/free",
        provider="openrouter",
        context_length=200_000,
        supports_tools=True,
        supports_structured_outputs=True,
        supports_reasoning_effort=True,
        meta_router=True,
        description="OpenRouter's own free meta-router (superseded by Aegis).",
    ),
    ModelInfo(
        id="google/lyria-3-pro-preview",
        provider="openrouter",
        context_length=1_048_576,
        supports_vision=True,
        text_out_only=False,
        description="Lyria 3 Pro — audio generation, not a chat model.",
    ),
    ModelInfo(
        id="google/lyria-3-clip-preview",
        provider="openrouter",
        context_length=1_048_576,
        supports_vision=True,
        text_out_only=False,
        description="Lyria 3 Clip — audio generation, not a chat model.",
    ),
)


@dataclass(slots=True)
class ModelCatalog:
    """The set of routable models plus where they came from."""

    models: dict[str, ModelInfo] = field(default_factory=dict)
    source: str = "empty"  # "live" | "cache" | "seed" | "declared"
    fetched_at: float = 0.0  # wall clock seconds

    # -- construction -------------------------------------------------------

    @classmethod
    def from_seed(cls) -> ModelCatalog:
        return cls(models={m.id: m for m in SEED_CATALOG}, source="seed", fetched_at=0.0)

    @classmethod
    def from_declared(cls, records: tuple[KeyRecord, ...]) -> ModelCatalog:
        """Catalog built purely from models declared in the keys file."""
        models: dict[str, ModelInfo] = {}
        for record in records:
            for dm in record.declared_models:
                models[dm.id] = ModelInfo(
                    id=dm.id,
                    provider=record.provider,
                    context_length=dm.context_length,
                    free=dm.free,
                    supports_tools=dm.supports_tools,
                    supports_vision=dm.supports_vision,
                    supports_structured_outputs=dm.supports_structured_outputs,
                )
        return cls(models=models, source="declared")

    def merge(self, other: ModelCatalog) -> None:
        """Fold another catalog in (declared endpoints join live data)."""
        for mid, model in other.models.items():
            existing = self.models.get(mid)
            if existing is None or existing.provider == model.provider:
                self.models[mid] = model

    # -- persistence --------------------------------------------------------

    def to_json(self) -> str:
        rows = [
            {
                "id": m.id,
                "provider": m.provider,
                "context_length": m.context_length,
                "free": m.free,
                "supports_tools": m.supports_tools,
                "supports_vision": m.supports_vision,
                "supports_structured_outputs": m.supports_structured_outputs,
                "supports_reasoning_effort": m.supports_reasoning_effort,
                "text_out_only": m.text_out_only,
                "meta_router": m.meta_router,
                "description": m.description,
            }
            for m in self.models.values()
        ]
        return json.dumps(
            {"fetched_at": self.fetched_at, "models": rows}, indent=2, ensure_ascii=False
        )

    @classmethod
    def from_json(cls, text: str) -> ModelCatalog:
        data = json.loads(text)
        models = {
            str(r["id"]): ModelInfo(
                id=str(r["id"]),
                provider=str(r.get("provider", "openrouter")),
                context_length=int(r.get("context_length", 8_192)),
                free=bool(r.get("free", True)),
                supports_tools=bool(r.get("supports_tools", False)),
                supports_vision=bool(r.get("supports_vision", False)),
                supports_structured_outputs=bool(r.get("supports_structured_outputs", False)),
                supports_reasoning_effort=bool(r.get("supports_reasoning_effort", False)),
                text_out_only=bool(r.get("text_out_only", True)),
                meta_router=bool(r.get("meta_router", False)),
                description=str(r.get("description", "")),
            )
            for r in data.get("models") or []
        }
        return cls(models=models, source="cache", fetched_at=float(data.get("fetched_at", 0.0)))

    def save(self, path: str | Path) -> None:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(self.to_json(), encoding="utf-8")
        tmp.replace(p)

    @classmethod
    def load(cls, path: str | Path, *, max_age_s: float) -> ModelCatalog | None:
        """Load the cache if it exists and is fresh enough."""
        p = Path(path).expanduser()
        if not p.is_file():
            return None
        try:
            cat = cls.from_json(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        if max_age_s > 0 and cat.fetched_at and (time.time() - cat.fetched_at) > max_age_s:
            return None
        return cat

    # -- access -------------------------------------------------------------

    def free_models(self) -> list[ModelInfo]:
        return [m for m in self.models.values() if m.free]

    def model(self, model_id: str) -> ModelInfo | None:
        return self.models.get(model_id)

    def diff(self, other: ModelCatalog) -> dict[str, list[str]]:
        """What changed between this catalog and ``other`` (for refresh)."""
        added = sorted(set(other.models) - set(self.models))
        removed = sorted(set(self.models) - set(other.models))
        return {"added": added, "removed": removed}


async def fetch_openrouter_catalog(client: Any) -> ModelCatalog:
    """Fetch the live model list. The endpoint is public; the client is
    an httpx.AsyncClient (or anything with a compatible ``get``)."""
    try:
        resp = await client.get(OPENROUTER_MODELS_URL)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        raise AegisError(
            "catalog fetch failed", context={"url": OPENROUTER_MODELS_URL, "cause": str(exc)}
        ) from exc
    models = parse_openrouter_models(payload)
    if not models:
        raise AegisError(
            "catalog fetch returned no models", context={"url": OPENROUTER_MODELS_URL}
        )
    return ModelCatalog(models={m.id: m for m in models}, source="live", fetched_at=time.time())


async def refresh_catalog(
    client: Any,
    cache_path: str | Path,
    *,
    ttl_s: float = 24 * 3600,
    declared: tuple[KeyRecord, ...] = (),
) -> tuple[ModelCatalog, dict[str, list[str]]]:
    """Best-effort refresh: live fetch, else fresh cache, else keep-old.

    Returns the new catalog and the diff against the previous cache so
    callers can report "2 new free models, 1 gone" instead of silence.
    """
    previous = ModelCatalog.load(cache_path, max_age_s=ttl_s)
    if previous is not None:
        return _with_declared(previous, declared), {"added": [], "removed": []}

    old = ModelCatalog.load(cache_path, max_age_s=0) or ModelCatalog.from_seed()
    try:
        fresh = await fetch_openrouter_catalog(client)
        fresh.save(cache_path)
    except AegisError:
        fresh = old if old.source in ("live", "cache") else ModelCatalog.from_seed()
        return _with_declared(fresh, declared), {"added": [], "removed": []}
    return _with_declared(fresh, declared), old.diff(fresh)


def _with_declared(catalog: ModelCatalog, records: tuple[KeyRecord, ...]) -> ModelCatalog:
    if records:
        catalog.merge(ModelCatalog.from_declared(records))
    return catalog
