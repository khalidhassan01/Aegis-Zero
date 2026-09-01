"""Selector domain types: categories, models, keys, health.

Pure data, no I/O. Everything the selector reasons about is expressed here
so the ranking, shielding, and learning layers stay interchangeable.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    """What kind of work a request is. Drives model choice."""

    CHAT = "chat"  # quick turns, summaries, formatting: latency matters
    REASONING = "reasoning"  # multi-step analysis, planning, math
    CODE = "code"  # writing and reviewing code, tool-calling agents
    VISION = "vision"  # requests that include images (or video frames)
    LONG_CONTEXT = "long_context"  # prompts beyond ~128k tokens
    EMBEDDING = "embedding"  # vector embeddings
    SAFETY = "safety"  # moderation / content-safety classification


#: Categories an LLM chat model can serve. EMBEDDING is handled separately.
CHAT_CATEGORIES = frozenset(
    {
        Category.CHAT,
        Category.REASONING,
        Category.CODE,
        Category.VISION,
        Category.LONG_CONTEXT,
        Category.SAFETY,
    }
)


def key_fingerprint(secret: str) -> str:
    """A stable, non-reversible id for an API key.

    State files may be read or shared; plaintext keys must never land in
    them. Fingerprints are also how the pool deduplicates a key that
    arrives via both the environment and the keys file.
    """
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One routable model, as discovered from a live catalog or a seed."""

    id: str  # canonical id, e.g. "z-ai/glm-5.2:free"
    provider: str  # owning provider id, e.g. "openrouter"
    context_length: int = 8_192
    free: bool = True  # zero prompt AND completion price
    supports_tools: bool = False
    supports_vision: bool = False
    supports_structured_outputs: bool = False
    supports_reasoning_effort: bool = False
    #: Output modality is text only (audio/video-out models are not chat
    #: models, whatever their input accepts).
    text_out_only: bool = True
    #: True for meta-models that route elsewhere themselves (e.g.
    #: "openrouter/free"). The selector supersedes them, so they are kept
    #: in the catalog but never routed to.
    meta_router: bool = False
    description: str = ""

    def fits(
        self,
        *,
        needs_tools: bool = False,
        needs_vision: bool = False,
        needs_structured: bool = False,
        min_context: int = 0,
    ) -> bool:
        """Hard capability filter: can this model serve this request at all?"""
        if self.meta_router or not self.text_out_only:
            return False
        if needs_tools and not self.supports_tools:
            return False
        if needs_vision and not self.supports_vision:
            return False
        if needs_structured and not self.supports_structured_outputs:
            return False
        return self.context_length >= min_context


@dataclass(frozen=True, slots=True)
class DeclaredModel:
    """A model declared by the user for a custom OpenAI-compatible endpoint.

    ``score`` is optional per-category knowledge (0-100); anything unset
    falls back to the neutral prior with size/feature nudges.
    """

    id: str
    context_length: int = 8_192
    supports_tools: bool = True
    supports_vision: bool = False
    supports_structured_outputs: bool = False
    free: bool = True
    scores: dict[str, float] = field(default_factory=dict)


class KeyState(str, Enum):
    """Health of one API key."""

    OK = "ok"
    COOLDOWN = "cooldown"  # rate limited; skip until `cooldown_until`
    QUARANTINED = "quarantined"  # auth/credit failure; human must fix
    UNPROBED = "unprobed"  # discovered but never verified live


def key_usable(state: KeyState) -> bool:
    """Whether a key may be *attempted* right now.

    UNPROBED counts as usable: discovery is trust-until-first-attempt and
    the first request is itself the probe — its outcome then updates
    health (429 -> cooldown, 401 -> quarantine, success -> OK). Keys
    that were unusable at discovery time would never be attempted at
    all, and a pool where nothing is attemptable cannot converge.
    """
    return state in (KeyState.OK, KeyState.UNPROBED)


@dataclass(slots=True)
class KeyHealth:
    """Mutable runtime health for one key. Never persisted with the secret."""

    state: KeyState = KeyState.UNPROBED
    #: Monotonic timestamp until which a COOLDOWN key must be skipped.
    cooldown_until: float = 0.0
    cooldown_reason: str = ""
    quarantined_reason: str = ""
    consecutive_failures: int = 0
    rate_limit_events: int = 0
    successes: int = 0
    failures: int = 0
    last_used: float = 0.0  # monotonic; drives fair round-robin

    def status(self, now: float) -> KeyState:
        """Effective state at ``now`` (a cooldown may have expired)."""
        if self.state is KeyState.COOLDOWN and now >= self.cooldown_until:
            return KeyState.OK
        return self.state


@dataclass(frozen=True, slots=True)
class KeyRecord:
    """One API key bound to a provider endpoint."""

    provider: str  # provider id, e.g. "openrouter"
    secret: str
    fingerprint: str
    base_url: str
    source: str = "env"  # "env" | "file:<path>"
    paid: bool = False
    declared_models: tuple[DeclaredModel, ...] = ()

    @property
    def label(self) -> str:
        return f"{self.provider}/{self.fingerprint}"


@dataclass(frozen=True, slots=True)
class Candidate:
    """A (model, key) pair the shield may attempt, with its explanation."""

    model: ModelInfo
    key: KeyRecord
    score: float
    why: str


@dataclass(frozen=True, slots=True)
class Decision:
    """The outcome of routing one request: what was chosen and the ladder."""

    category: Category
    candidates: tuple[Candidate, ...]
    chosen: Candidate | None = None

    @property
    def model_id(self) -> str:
        return self.chosen.model.id if self.chosen else ""


@dataclass(frozen=True, slots=True)
class AttemptReport:
    """What one shielded execution actually did, for logs and learning."""

    model: str
    key_fingerprint: str
    outcome: str  # "success" | "rate_limited" | "auth" | "error" | "timeout"
    latency_ms: float
    retry_after: float | None = None
    detail: str = ""
    at: float = field(default_factory=time.time)
