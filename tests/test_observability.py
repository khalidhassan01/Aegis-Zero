from __future__ import annotations

import json

from aegis_zero.core.events import Event, EventBus, EventType, NullBus
from aegis_zero.observability import (
    Metrics,
    TraceRecorder,
    configure_logging,
    instrument,
)


def ev(kind: EventType, **data) -> Event:
    return Event(type=kind, run_id="run_abc", data=data)


async def test_bus_delivers_to_subscribers():
    bus = EventBus()
    seen = []
    bus.subscribe(seen.append)
    await bus.publish(ev(EventType.RUN_START))
    assert len(seen) == 1


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    seen = []
    off = bus.subscribe(seen.append)
    off()
    await bus.publish(ev(EventType.RUN_START))
    assert seen == []


async def test_async_subscribers_are_awaited():
    bus = EventBus()
    seen = []

    async def handler(e):
        seen.append(e)

    bus.subscribe(handler)
    await bus.publish(ev(EventType.RUN_START))
    assert len(seen) == 1


async def test_null_bus_is_inert():
    bus = NullBus()
    seen = []
    bus.subscribe(seen.append)
    await bus.publish(ev(EventType.RUN_START))
    assert seen == []


def test_metrics_track_tools_and_failures():
    m = Metrics()
    m.observe(ev(EventType.RUN_START))
    m.observe(ev(EventType.TOOL_END, tool="calc", ok=True))
    m.observe(ev(EventType.TOOL_END, tool="calc", ok=False))
    snap = m.snapshot()
    assert snap["tool_calls"] == 2
    assert snap["tool_failures"] == 1
    assert snap["per_tool"]["calc"] == 2


def test_metrics_percentiles():
    m = Metrics()
    for i in range(100):
        m.observe(ev(EventType.LLM_END, tokens=10, latency_ms=float(i)))
    snap = m.snapshot()
    assert snap["tokens"] == 1000
    assert 40 <= snap["latency_p50_ms"] <= 60
    assert snap["latency_p95_ms"] >= 90


def test_metrics_count_policy_denials():
    m = Metrics()
    m.observe(ev(EventType.POLICY_DECISION, decision="deny", tool="shell"))
    m.observe(ev(EventType.APPROVAL_RESULT, granted=False))
    snap = m.snapshot()
    assert snap["policy_denials"] == 1 and snap["approvals_denied"] == 1


def test_trace_recorder_writes_jsonl(tmp_path):
    path = tmp_path / "t" / "trace.jsonl"
    rec = TraceRecorder(path)
    rec(ev(EventType.RUN_START, goal="g"))
    rec(ev(EventType.RUN_END, ok=True))
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["type"] == "run.start" and rows[0]["run_id"] == "run_abc"


def test_json_logging_redacts_secrets(caplog):
    import io
    stream = io.StringIO()
    log = configure_logging("INFO", json_format=True, stream=stream)
    log.info("key is sk-abcdefghijklmnopqrstuv here")
    payload = json.loads(stream.getvalue())
    assert "sk-abcdef" not in payload["message"]
    assert "[REDACTED]" in payload["message"]


async def test_instrument_wires_everything(tmp_path):
    bus = EventBus()
    m = instrument(bus, trace_path=tmp_path / "trace.jsonl")
    await bus.publish(ev(EventType.RUN_START, goal="g"))
    assert m.snapshot()["runs"] == 1
    assert (tmp_path / "trace.jsonl").exists()
