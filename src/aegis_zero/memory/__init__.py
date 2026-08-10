"""Memory subsystem: vector stores and reinforcement-weighted retrieval."""

from ..core.config import MemorySettings
from ..core.errors import ConfigError
from .memrl import (
    Embedder,
    MemRLConfig,
    MemRLEngine,
    RankedMemory,
    signal_from_outcome,
    signal_from_text,
)
from .store import Hit, InMemoryStore, QdrantStore, VectorStore, cosine

__all__ = [
    "Embedder",
    "Hit",
    "InMemoryStore",
    "MemRLConfig",
    "MemRLEngine",
    "QdrantStore",
    "RankedMemory",
    "VectorStore",
    "build_store",
    "cosine",
    "signal_from_outcome",
    "signal_from_text",
]


def build_store(settings: MemorySettings) -> VectorStore:
    backend = settings.backend.lower()
    if backend in ("memory", "inmemory", "local"):
        return InMemoryStore()
    if backend == "qdrant":
        return QdrantStore(
            url=settings.url, collection=settings.collection, vector_size=settings.vector_size
        )
    raise ConfigError("unknown memory backend", context={"backend": settings.backend})
