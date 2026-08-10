from __future__ import annotations

import asyncio

import pytest

from aegis_zero.core.errors import ToolError, ToolNotFound
from aegis_zero.core.models import Risk
from aegis_zero.tools.registry import ToolRegistry, build_parameters


def test_schema_derived_from_signature():
    def fn(
        name: str,
        count: int = 3,
        ratio: float = 1.0,
        flag: bool = False,
        tags: list[str] | None = None,
    ) -> str:
        """Docstring first line."""
        return name

    schema = build_parameters(fn)
    props = schema["properties"]
    assert props["name"] == {"type": "string"}
    assert props["count"] == {"type": "integer"}
    assert props["ratio"] == {"type": "number"}
    assert props["flag"] == {"type": "boolean"}
    assert props["tags"]["type"] == "array"
    assert schema["required"] == ["name"]


def test_decorator_registers_with_docstring():
    r = ToolRegistry()

    @r.tool(risk=Risk.LOW)
    def greet(who: str) -> str:
        """Say hello to someone."""
        return f"hi {who}"

    spec = r.get("greet")
    assert spec.risk is Risk.LOW
    assert spec.description == "Say hello to someone."
    assert r.get("greet").to_openai_schema()["function"]["name"] == "greet"


def test_duplicate_registration_rejected():
    r = ToolRegistry()
    r.tool()(lambda: None.__class__)
    with pytest.raises(ToolError):

        @r.tool(name="<lambda>")
        def other():
            return 1


def test_unknown_tool_raises():
    with pytest.raises(ToolNotFound):
        ToolRegistry().get("nope")


async def test_execute_sync_tool():
    r = ToolRegistry()

    @r.tool()
    def double(x: int) -> int:
        return x * 2

    res = await r.execute("double", {"x": 21})
    assert res.ok and res.output == 42
    assert res.duration_ms >= 0


async def test_execute_async_tool():
    r = ToolRegistry()

    @r.tool()
    async def slow(x: int) -> int:
        await asyncio.sleep(0)
        return x + 1

    assert (await r.execute("slow", {"x": 1})).output == 2


async def test_missing_required_argument_fails_cleanly():
    r = ToolRegistry()

    @r.tool()
    def need(a: str) -> str:
        return a

    res = await r.execute("need", {})
    assert not res.ok and "missing required" in res.error


async def test_unknown_arguments_are_dropped():
    r = ToolRegistry()

    @r.tool()
    def only(a: str) -> str:
        return a

    res = await r.execute("only", {"a": "x", "injected": "bad"})
    assert res.ok and res.output == "x"


async def test_exception_becomes_failed_result_not_raise():
    r = ToolRegistry()

    @r.tool()
    def boom() -> str:
        raise ValueError("kaput")

    res = await r.execute("boom", {})
    assert not res.ok and "ValueError: kaput" in res.error


async def test_timeout_is_enforced():
    r = ToolRegistry()

    @r.tool(timeout=0.05)
    async def hang() -> str:
        await asyncio.sleep(5)
        return "never"

    res = await r.execute("hang", {})
    assert not res.ok and "timed out" in res.error


async def test_unknown_tool_execute_is_soft_failure():
    res = await ToolRegistry().execute("ghost", {})
    assert not res.ok and "no such tool" in res.error
