from __future__ import annotations

from aegis_zero.core.models import Message
from aegis_zero.memory import Embedder, InMemoryStore, MemRLEngine
from aegis_zero.orchestrator.context import ContextBuilder, estimate_tokens
from aegis_zero.providers import EchoProvider


async def test_system_prompt_is_first():
    packet = await ContextBuilder().build("goal", [], system="SYS")
    msgs = packet.to_messages()
    assert msgs[0].role == "system" and msgs[0].content.startswith("SYS")


async def test_recent_messages_always_survive_trimming():
    builder = ContextBuilder(max_tokens=60, keep_recent=2)
    history = [Message(role="user", content="x" * 400) for _ in range(20)]
    history.append(Message(role="user", content="MOST_RECENT"))
    packet = await builder.build("goal", history, system="SYS")
    assert any("MOST_RECENT" in m.content for m in packet.messages)


async def test_elision_is_announced_not_silent():
    builder = ContextBuilder(max_tokens=50, keep_recent=1)
    history = [Message(role="user", content="y" * 800) for _ in range(10)]
    packet = await builder.build("goal", history, system="SYS")
    assert any("elided" in m.content for m in packet.messages)


async def test_short_history_is_untouched():
    history = [Message(role="user", content="a"), Message(role="user", content="b")]
    packet = await ContextBuilder(max_tokens=10_000).build("g", history, system="S")
    assert [m.content for m in packet.messages] == ["a", "b"]


async def test_memories_are_injected_and_tracked():
    mem = MemRLEngine(InMemoryStore(), Embedder(EchoProvider(vector_size=32), "e"))
    ep = await mem.remember("Rabat is the capital of Morocco")
    packet = await ContextBuilder(mem).build("Rabat is the capital of Morocco",
                                             [], system="SYS")
    assert "Rabat" in packet.system
    assert ep.id in packet.memory_ids


async def test_memory_failure_degrades_gracefully():
    class Broken(MemRLEngine):
        async def recall(self, *a, **kw):
            raise RuntimeError("store down")

    mem = Broken(InMemoryStore(), Embedder(EchoProvider(), "e"))
    packet = await ContextBuilder(mem).build("g", [], system="SYS")
    assert packet.system.startswith("SYS") and packet.memories == []


async def test_extra_context_rendered():
    packet = await ContextBuilder().build("g", [], system="S",
                                          extra={"reconnaissance": "notes here"})
    assert "notes here" in packet.system


def test_token_estimate_scales():
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 400) == 100
