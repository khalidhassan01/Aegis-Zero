"""Structured tracing, metrics, and JSONL trace export."""
from __future__ import annotations

import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from ..core.events import Event, EventBus, EventType
from ..tools.policy import redact


def configure_logging(level: str = "INFO", *, json_format: bool = False,
                      stream: TextIO | None = None) -> logging.Logger:
    """Configure the ``aegis`` logger. Idempotent."""
    logger = logging.getLogger("aegis")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    if json_format:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"
        ))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.time(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


@dataclass(slots=True)
class Metrics:
    """In-process counters aggregated from the event stream."""

    runs: int = 0
    runs_failed: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    approvals_requested: int = 0
    approvals_denied: int = 0
    policy_denials: int = 0
    tokens: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    per_tool: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def observe(self, event: Event) -> None:
        d = event.data
        if event.type is EventType.RUN_START:
            self.runs += 1
        elif event.type is EventType.RUN_ERROR or (
            event.type is EventType.RUN_END and not d.get("ok", True)
        ):
            self.runs_failed += 1
        elif event.type is EventType.LLM_END:
            self.llm_calls += 1
            self.tokens += int(d.get("tokens") or 0)
            if d.get("latency_ms"):
                self.latencies_ms.append(float(d["latency_ms"]))
        elif event.type is EventType.TOOL_END:
            self.tool_calls += 1
            self.per_tool[str(d.get("tool"))] += 1
            if not d.get("ok", True):
                self.tool_failures += 1
        elif event.type is EventType.APPROVAL_REQUEST:
            self.approvals_requested += 1
        elif event.type is EventType.APPROVAL_RESULT and not d.get("granted"):
            self.approvals_denied += 1
        elif event.type is EventType.POLICY_DECISION and d.get("decision") == "deny":
            self.policy_denials += 1

    def snapshot(self) -> dict[str, Any]:
        lat = sorted(self.latencies_ms)
        def pct(p: float) -> float:
            if not lat:
                return 0.0
            return round(lat[min(len(lat) - 1, int(len(lat) * p))], 1)
        return {
            "runs": self.runs, "runs_failed": self.runs_failed,
            "llm_calls": self.llm_calls, "tool_calls": self.tool_calls,
            "tool_failures": self.tool_failures, "tokens": self.tokens,
            "approvals_requested": self.approvals_requested,
            "approvals_denied": self.approvals_denied,
            "policy_denials": self.policy_denials,
            "latency_p50_ms": pct(0.5), "latency_p95_ms": pct(0.95),
            "per_tool": dict(self.per_tool),
        }


class TraceRecorder:
    """Appends every event to a JSONL file, one file per process."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, event: Event) -> None:
        row = {"ts": event.at, "type": event.type.value,
               "run_id": event.run_id, "data": event.data}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


class LogSubscriber:
    """Human-readable log lines from the event stream."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.log = logger or logging.getLogger("aegis")

    def __call__(self, event: Event) -> None:
        d = event.data
        t = event.type
        short = event.run_id[-6:] if event.run_id else "------"
        if t is EventType.RUN_START:
            goal = redact(str(d.get("goal", "")))[:120]
            self.log.info("[%s] run start: %s", short, goal)
        elif t is EventType.RUN_END:
            self.log.info("[%s] run end: %s", short, d)
        elif t is EventType.LLM_END:
            self.log.debug("[%s] llm %s tokens=%s %sms", short, d.get("step"),
                           d.get("tokens"), d.get("latency_ms"))
        elif t is EventType.TOOL_END:
            level = self.log.debug if d.get("ok") else self.log.warning
            level("[%s] tool %s ok=%s %s", short, d.get("tool"),
                  d.get("ok"), d.get("error") or "")
        elif t is EventType.POLICY_DECISION and d.get("decision") in ("deny", "approve"):
            self.log.warning("[%s] policy %s on %s: %s", short, d.get("decision"),
                             d.get("tool"), d.get("reason"))
        elif t is EventType.RUN_ERROR:
            self.log.error("[%s] run error: %s", short, d.get("error"))


def instrument(bus: EventBus, *, metrics: Metrics | None = None,
               trace_path: str | Path | None = None,
               logger: logging.Logger | None = None) -> Metrics:
    """Attach logging, metrics, and optional trace recording to a bus."""
    m = metrics or Metrics()
    bus.subscribe(m.observe)
    bus.subscribe(LogSubscriber(logger))
    if trace_path:
        bus.subscribe(TraceRecorder(trace_path))
    return m
