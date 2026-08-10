from __future__ import annotations

from aegis_zero.core.models import (
    Message,
    Risk,
    ToolCall,
    ToolResult,
    Usage,
    new_id,
)


def test_risk_is_ordered():
    assert Risk.SAFE.level < Risk.LOW.level < Risk.MEDIUM.level
    assert Risk.HIGH.level < Risk.CRITICAL.level


def test_usage_adds():
    total = Usage(10, 5) + Usage(1, 2)
    assert (total.prompt_tokens, total.completion_tokens) == (11, 7)
    assert total.total_tokens == 18


def test_message_wire_roundtrip():
    msg = Message(
        role="assistant",
        content="hi",
        tool_calls=(ToolCall(name="calc", arguments={"x": 1}, id="c1"),),
    )
    wire = msg.to_wire()
    assert wire["role"] == "assistant"
    assert wire["tool_calls"][0]["function"]["name"] == "calc"
    assert wire["tool_calls"][0]["id"] == "c1"


def test_tool_call_arguments_serialise_as_json_string():
    """Regression: Ollama and vLLM reject an object for `arguments`."""
    import json as _json

    msg = Message(
        role="assistant", tool_calls=(ToolCall(name="f", arguments={"a": 1}, id="c1"),)
    )
    raw = msg.to_wire()["tool_calls"][0]["function"]["arguments"]
    assert isinstance(raw, str)
    assert _json.loads(raw) == {"a": 1}


def test_tool_result_error_message_is_marked():
    res = ToolResult(tool="t", ok=False, error="boom", call_id="c1")
    msg = res.as_message()
    assert msg.role == "tool" and "ERROR: boom" in msg.content
    assert msg.tool_call_id == "c1"


def test_ids_are_unique_and_prefixed():
    ids = {new_id("run") for _ in range(200)}
    assert len(ids) == 200
    assert all(i.startswith("run_") for i in ids)
