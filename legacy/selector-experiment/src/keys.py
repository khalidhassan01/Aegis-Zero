"""API key pool: discovery, dedup, health, cooldowns, quarantine.

The pool is the "grows with every new key" layer. Keys arrive from two
places and are folded together by fingerprint:

* environment variables matching a known provider profile
  (``OPENROUTER_API_KEY``, ``GROQ_API_KEY``, ...),
* a user-owned YAML file (``~/.config/aegis-zero/keys.yaml``) that may
  also declare custom OpenAI-compatible endpoints and their models.

Adding a key is therefore: export the env var or drop a line in the file.
The next process start discovers it, probes it lazily, and starts using
it. No code changes, ever.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.errors import ConfigError
from .types import (
    DeclaredModel,
    KeyHealth,
    KeyRecord,
    KeyState,
    key_fingerprint,
    key_usable,
)

#: Monotonic clock, injectable for deterministic tests.
Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class ProviderProfile:
    """Static knowledge about a known API provider."""

    id: str
    base_url: str
    env_names: tuple[str, ...]
    paid: bool = False  # no free tier at all -> excluded by free_only
    #: Whether the provider exposes a model catalog worth fetching.
    has_catalog: bool = False
    notes: str = ""


#: Curated provider profiles. Custom endpoints come from the keys file.
PROVIDER_PROFILES: dict[str, ProviderProfile] = {
    p.id: p
    for p in (
        ProviderProfile(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            env_names=("OPENROUTER_API_KEY",),
            has_catalog=True,
            notes="aggregates hundreds of models; :free ids are zero-cost",
        ),
        ProviderProfile(
            id="deepseek",
            base_url="https://api.deepseek.com/v1",
            env_names=("DEEPSEEK_API_KEY",),
            paid=True,
            notes="official DeepSeek API is pay-per-token; excluded unless allow_paid",
        ),
        ProviderProfile(
            id="groq",
            base_url="https://api.groq.com/openai/v1",
            env_names=("GROQ_API_KEY",),
            has_catalog=True,
            notes="generous free tier, very fast inference",
        ),
        ProviderProfile(
            id="mistral",
            base_url="https://api.mistral.ai/v1",
            env_names=("MISTRAL_API_KEY",),
            has_catalog=True,
            notes="free tier on La Plateforme",
        ),
        ProviderProfile(
            id="together",
            base_url="https://api.together.xyz/v1",
            env_names=("TOGETHER_API_KEY",),
            notes="free models exist but are credited, not zero-price",
        ),
        ProviderProfile(
            id="cerebras",
            base_url="https://api.cerebras.ai/v1",
            env_names=("CEREBRAS_API_KEY",),
            has_catalog=True,
            notes="free tier, extremely fast",
        ),
        ProviderProfile(
            id="huggingface",
            base_url="https://router.huggingface.co/v1",
            env_names=("HF_TOKEN", "HUGGINGFACE_API_KEY"),
            has_catalog=True,
            notes="serverless inference; small free monthly credits",
        ),
        ProviderProfile(
            id="google",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            env_names=("GEMINI_API_KEY", "GOOGLE_API_KEY"),
            has_catalog=True,
            notes="free tier on Gemini models",
        ),
    )
}

#: Default cooldown when a 429 carries no usable Retry-After.
DEFAULT_RATE_LIMIT_COOLDOWN_S = 60.0


def _load_keys_file(path: str | Path | None) -> dict[str, Any]:
    """Read and validate the keys YAML. Missing file is an empty pool."""
    if not path:
        return {}
    p = Path(path).expanduser()
    if not p.is_file():
        return {}
    try:
        import yaml

        loaded = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ConfigError(
            "invalid keys file", context={"path": str(p), "cause": str(exc)}
        ) from exc

    if isinstance(loaded, dict) and "providers" in loaded:
        loaded = loaded["providers"]
    if not isinstance(loaded, dict):
        raise ConfigError(
            "keys file root must be a mapping of providers", context={"path": str(p)}
        )
    return loaded


def _declared_models(raw: Any) -> tuple[DeclaredModel, ...]:
    if not raw:
        return ()
    out: list[DeclaredModel] = []
    for item in raw:
        if isinstance(item, str):
            out.append(DeclaredModel(id=item))
            continue
        if not isinstance(item, Mapping):
            raise ConfigError("models entries must be strings or mappings")
        scores = item.get("scores") or {}
        out.append(
            DeclaredModel(
                id=str(item.get("id", "")),
                context_length=int(item.get("context_length", 8_192)),
                supports_tools=bool(item.get("tools", True)),
                supports_vision=bool(item.get("vision", False)),
                supports_structured_outputs=bool(item.get("structured", False)),
                free=bool(item.get("free", True)),
                scores={str(k): float(v) for k, v in scores.items()},
            )
        )
    return tuple(out)


def discover_keys(
    env: Mapping[str, str],
    keys_file: str | Path | None = None,
    *,
    allow_paid: bool = False,
) -> list[KeyRecord]:
    """Find every usable key: env-var profiles first, then the keys file.

    A key found twice (same provider + same secret) is one record. Custom
    file providers may declare their own base_url and models; env-profile
    providers use the curated profile above.
    """
    seen: dict[tuple[str, str], KeyRecord] = {}
    records: list[KeyRecord] = []

    for profile in PROVIDER_PROFILES.values():
        for name in profile.env_names:
            secret = (env.get(name) or "").strip()
            if not secret:
                continue
            fp = key_fingerprint(secret)
            if (profile.id, fp) in seen:
                continue
            record = KeyRecord(
                provider=profile.id,
                secret=secret,
                fingerprint=fp,
                base_url=profile.base_url,
                source=f"env:{name}",
                paid=profile.paid,
            )
            seen[(profile.id, fp)] = record
            records.append(record)

    for provider_id, spec in _load_keys_file(keys_file).items():
        if not isinstance(spec, Mapping):
            raise ConfigError(
                "provider entry must be a mapping",
                context={"provider": str(provider_id)},
            )
        api_key = str(spec.get("api_key") or "").strip()
        env_name = str(spec.get("api_key_env") or "").strip()
        if not api_key and env_name:
            api_key = (env.get(env_name) or "").strip()
        if not api_key:
            continue  # declared but no secret available (yet) - fine
        fp = key_fingerprint(api_key)
        if (provider_id, fp) in seen:
            continue
        known: ProviderProfile | None = PROVIDER_PROFILES.get(provider_id)
        base_url = str(spec.get("base_url") or (known.base_url if known else "")).rstrip("/")
        if not base_url:
            raise ConfigError(
                "custom provider entry needs a base_url",
                context={"provider": str(provider_id)},
            )
        record = KeyRecord(
            provider=provider_id,
            secret=api_key,
            fingerprint=fp,
            base_url=base_url,
            source="file",
            paid=bool(spec.get("paid", known.paid if known else False)),
            declared_models=_declared_models(spec.get("models")),
        )
        seen[(provider_id, fp)] = record
        records.append(record)

    if not allow_paid:
        records = [r for r in records if not r.paid]
    return records


class KeyPool:
    """Runtime registry of keys with health, cooldowns, and fair picking.

    Selection policy for ``acquire``: healthy keys first (a cooldown that
    has expired counts as healthy again), then least-recently-used, then
    fewest recent rate-limit events. LRU spreads load across the pool so
    one key is never hammered into a 429 while its siblings sit idle.
    """

    def __init__(self, records: Iterable[KeyRecord], *, clock: Clock = time.monotonic) -> None:
        self._records: dict[str, KeyRecord] = {}
        self._health: dict[str, KeyHealth] = {}
        self._clock = clock
        for r in records:
            self.add(r)

    def add(self, record: KeyRecord) -> KeyRecord | None:
        """Register a key. Returns None if it is already known."""
        if record.fingerprint in self._records:
            return None
        self._records[record.fingerprint] = record
        self._health[record.fingerprint] = KeyHealth()
        return record

    @property
    def records(self) -> tuple[KeyRecord, ...]:
        return tuple(self._records.values())

    def record(self, fingerprint: str) -> KeyRecord | None:
        return self._records.get(fingerprint)

    def for_provider(self, provider: str) -> tuple[KeyRecord, ...]:
        return tuple(r for r in self._records.values() if r.provider == provider)

    def health(self, fingerprint: str) -> KeyHealth:
        return self._health[fingerprint]

    def clock(self) -> float:
        """The pool's monotonic clock (shared with cooldown checks)."""
        return self._clock()

    def providers(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(r.provider for r in self._records.values()))

    def acquire(self, provider: str | None = None) -> KeyRecord | None:
        """Pick the best available key, or None if everything is blocked.

        "Available" skips quarantined keys and keys still in cooldown; a
        freshly discovered (unprobed) key is available — its first
        request is the probe. Among the available keys it prefers the
        least recently used so concurrent requests fan out across the
        pool instead of piling onto one key.
        """
        now = self._clock()
        best: KeyRecord | None = None
        best_rank: tuple[int, float, int, str] | None = None
        for record in self._records.values():
            if provider and record.provider != provider:
                continue
            h = self._health[record.fingerprint]
            if not key_usable(h.status(now)):
                continue
            # Lower rank is better: never-used first, then LRU, then
            # fewest rate-limit scars, then stable fingerprint order.
            rank = (int(h.last_used > 0), h.last_used, h.rate_limit_events, record.fingerprint)
            if best_rank is None or rank < best_rank:
                best, best_rank = record, rank
        if best is not None:
            self._health[best.fingerprint].last_used = now
        return best

    def mark_used(self, fingerprint: str) -> None:
        self._health[fingerprint].last_used = self._clock()

    def report_rate_limited(
        self, fingerprint: str, *, retry_after: float | None = None
    ) -> float:
        """Put a key on cooldown. Returns the cooldown seconds applied."""
        h = self._health[fingerprint]
        seconds = max(retry_after or 0.0, 1.0)
        if retry_after is None:
            seconds = DEFAULT_RATE_LIMIT_COOLDOWN_S
        h.state = KeyState.COOLDOWN
        h.cooldown_until = self._clock() + seconds
        h.cooldown_reason = "rate limited"
        h.rate_limit_events += 1
        return seconds

    def report_auth_failure(self, fingerprint: str, reason: str) -> None:
        """Quarantine a key: 401/403/402 means a human must fix it."""
        h = self._health[fingerprint]
        h.state = KeyState.QUARANTINED
        h.quarantined_reason = reason

    def report_probe(self, fingerprint: str, ok: bool) -> None:
        """Record the outcome of an explicit key probe."""
        h = self._health[fingerprint]
        if ok:
            h.state = KeyState.OK
            h.consecutive_failures = 0
        else:
            h.consecutive_failures += 1

    def report_success(self, fingerprint: str) -> None:
        h = self._health[fingerprint]
        # A key that just served a request is verified live, whatever it
        # was before (unprobed -> ok). Cooldown/quarantine are unreachable
        # here: those keys are never attempted.
        h.state = KeyState.OK
        h.consecutive_failures = 0
        h.successes += 1

    def report_failure(self, fingerprint: str) -> None:
        h = self._health[fingerprint]
        h.failures += 1
        h.consecutive_failures += 1

    def restore(self, fingerprint: str) -> bool:
        """Lift a quarantine or cooldown (manual, e.g. after fixing a key)."""
        h = self._health.get(fingerprint)
        if h is None:
            return False
        h.state = KeyState.OK
        h.cooldown_until = 0.0
        h.quarantined_reason = ""
        h.consecutive_failures = 0
        return True

    def snapshot(self) -> list[dict[str, Any]]:
        """Human-readable pool status. Contains fingerprints, never secrets."""
        now = self._clock()
        out = []
        for fp, record in self._records.items():
            h = self._health[fp]
            state = h.status(now)
            entry: dict[str, Any] = {
                "key": record.label,
                "provider": record.provider,
                "source": record.source,
                "state": state.value,
                "rate_limit_events": h.rate_limit_events,
                "successes": h.successes,
                "failures": h.failures,
            }
            if state is KeyState.COOLDOWN:
                entry["cooldown_s_left"] = round(max(h.cooldown_until - now, 0.0), 1)
            if state is KeyState.QUARANTINED:
                entry["reason"] = h.quarantined_reason
            out.append(entry)
        return sorted(out, key=lambda e: (e["state"] != "ok", e["key"]))

    def earliest_cooldown_end(self) -> float | None:
        """When the soonest cooldown lifts (for wait-and-retry), if any."""
        now = self._clock()
        ends = [
            h.cooldown_until
            for h in self._health.values()
            if h.state is KeyState.COOLDOWN and h.cooldown_until > now
        ]
        return min(ends) if ends else None
