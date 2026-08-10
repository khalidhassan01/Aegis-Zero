from __future__ import annotations

import pytest

from aegis_zero.core.events import EventBus
from aegis_zero.memory import Embedder, InMemoryStore, MemRLEngine
from aegis_zero.providers import EchoProvider
from aegis_zero.tools import AutoApprove, PolicyEngine, default_registry


@pytest.fixture
def provider() -> EchoProvider:
    return EchoProvider()


@pytest.fixture
def registry():
    return default_registry(enable_http=True)


@pytest.fixture
def policy():
    return PolicyEngine(resolve_host=lambda h: ["93.184.216.34"])


@pytest.fixture
def memory(provider):
    return MemRLEngine(InMemoryStore(), Embedder(provider, model="e"))


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def approve():
    return AutoApprove()
