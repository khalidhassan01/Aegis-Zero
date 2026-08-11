"""Layered configuration: defaults < YAML file < environment.

No module-level I/O. Call ``load_settings()`` explicitly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .errors import ConfigError

ENV_PREFIX = "AEGIS_"


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    kind: str = "openai"  # openai | ollama | echo
    base_url: str = "http://127.0.0.1:8001/v1"
    api_key: str = ""
    timeout: float = 120.0
    max_retries: int = 3


@dataclass(frozen=True, slots=True)
class ModelSettings:
    fast: str = "qwen2.5:7b"
    deep: str = "qwen2.5:7b"
    code: str = "qwen2.5-coder:7b"
    embed: str = "nomic-embed-text"
    fallback_chain: tuple[str, ...] = ("qwen2.5:3b", "qwen2.5:1.5b")
    primary_fallback_attempts: int = 1  # retries on the primary before degrading
    # Per-model context windows (audit #13): ``max_tokens`` was a single
    # global constant, so the prompt budget was wrong for every model that
    # was not the one it was tuned for. Each model reports a different
    # window, and the prompt budget is now derived per model. Names match
    # the model id sent to the provider; an unknown model falls back to
    # ``default_context_window`` (kept conservative on purpose).
    context_windows: dict[str, int] = field(
        default_factory=lambda: {
            "qwen2.5:1.5b": 32_768,
            "qwen2.5:3b": 32_768,
            "qwen2.5:7b": 32_768,
            "qwen2.5-coder:7b": 32_768,
        }
    )
    default_context_window: int = 8_192
    # Tokens reserved for the model's own generation when deriving the
    # prompt budget from a context window.
    generation_reserve: int = 4_096

    def context_window(self, model: str) -> int:
        """The context window for ``model`` (or a conservative default)."""
        return self.context_windows.get(model, self.default_context_window)

    def prompt_budget(self, model: str) -> int:
        """How many prompt tokens a single call to ``model`` may use.

        Derived from that model's own window minus a reserve for the
        answer, never below the reserve (so a tiny window never yields a
        negative prompt budget).
        """
        return max(self.context_window(model) - self.generation_reserve, 512)


@dataclass(frozen=True, slots=True)
class MemorySettings:
    backend: str = "memory"  # memory | qdrant
    url: str = "http://127.0.0.1:6333"
    collection: str = "aegis_episodes"
    vector_size: int = 768
    top_k: int = 6


@dataclass(frozen=True, slots=True)
class PolicySettings:
    approval_threshold: str = "high"  # min risk tier requiring approval
    allow_network: bool = True
    allowed_roots: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Settings:
    provider: ProviderSettings = field(default_factory=ProviderSettings)
    models: ModelSettings = field(default_factory=ModelSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    policy: PolicySettings = field(default_factory=PolicySettings)
    max_steps: int = 24
    max_seconds: float = 600.0
    max_tokens: int = 200_000
    log_level: str = "INFO"
    trace_dir: str = ""
    harness_path: str = ""

    def with_overrides(self, **kw: Any) -> Settings:
        return replace(self, **kw)


_SECTIONS = {
    "provider": ProviderSettings,
    "models": ModelSettings,
    "memory": MemorySettings,
    "policy": PolicySettings,
}


def _coerce(target_type: Any, raw: Any) -> Any:
    """Coerce a scalar from YAML/env into the dataclass field type."""
    if target_type is bool:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if target_type is int:
        return int(raw)
    if target_type is float:
        return float(raw)
    if target_type is tuple or getattr(target_type, "__origin__", None) is tuple:
        if isinstance(raw, str):
            return tuple(p.strip() for p in raw.split(",") if p.strip())
        return tuple(raw)
    if target_type is dict or getattr(target_type, "__origin__", None) is dict:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            import json

            return json.loads(raw)
        return dict(raw)
    return str(raw)


def _build(cls: Any, data: dict[str, Any]) -> Any:
    hints = {f.name: f.type for f in cls.__dataclass_fields__.values()}
    kwargs = {}
    for key, value in data.items():
        if key not in hints:
            raise ConfigError("unknown setting", context={"section": cls.__name__, "key": key})
        kwargs[key] = _coerce(_resolve_type(hints[key]), value)
    return cls(**kwargs)


def _resolve_type(hint: Any) -> Any:
    """Map a (possibly string) annotation to a coercion target.

    Container generics are checked before scalars on purpose: a substring
    match like ``"int"`` inside ``"dict[str, int]"`` must not win, so the
    container type is resolved first.
    """
    text = hint if isinstance(hint, str) else getattr(hint, "__name__", str(hint))
    if "dict" in text:
        return dict
    if "tuple" in text:
        return tuple
    if "bool" in text:
        return bool
    if "int" in text:
        return int
    if "float" in text:
        return float
    return str


def _from_env(env: dict[str, str]) -> dict[str, dict[str, Any]]:
    """AEGIS_PROVIDER__BASE_URL=... -> {'provider': {'base_url': ...}}"""
    out: dict[str, dict[str, Any]] = {}
    for raw_key, value in env.items():
        if not raw_key.startswith(ENV_PREFIX):
            continue
        body = raw_key[len(ENV_PREFIX) :].lower()
        if "__" in body:
            section, _, field_name = body.partition("__")
        else:
            section, field_name = "", body
        out.setdefault(section, {})[field_name] = value
    return out


def load_settings(
    path: str | Path | None = None, env: dict[str, str] | None = None
) -> Settings:
    """Build Settings from defaults, an optional YAML file, then environment."""
    env = os.environ.copy() if env is None else dict(env)
    data: dict[str, Any] = {}

    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            raise ConfigError("config file not found", context={"path": str(p)})
        data = _read_yaml(p)

    for section, overrides in _from_env(env).items():
        if section == "":
            data.update(overrides)
        else:
            if section not in _SECTIONS:
                continue
            merged = dict(data.get(section) or {})
            merged.update(overrides)
            data[section] = merged

    kwargs: dict[str, Any] = {}
    for name, cls in _SECTIONS.items():
        kwargs[name] = _build(cls, dict(data.pop(name, None) or {}))

    top_hints = {f.name: f.type for f in Settings.__dataclass_fields__.values()}
    for key, value in data.items():
        if key not in top_hints:
            raise ConfigError("unknown top-level setting", context={"key": key})
        kwargs[key] = _coerce(_resolve_type(top_hints[key]), value)

    return Settings(**kwargs)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ConfigError("PyYAML required to read config files") from exc
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ConfigError("invalid YAML", context={"path": str(path)}) from exc
    if not isinstance(loaded, dict):
        raise ConfigError("config root must be a mapping", context={"path": str(path)})
    return loaded
