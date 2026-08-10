"""Tool registry with JSON-Schema generation from type hints.

Tools are plain (async or sync) functions decorated with ``@tool``. The
schema handed to the model is derived from the signature, so the code and
the contract cannot drift apart.
"""
from __future__ import annotations

import asyncio
import inspect
import time
import typing
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.errors import ToolError, ToolNotFound, ToolTimeout, ToolValidationError
from ..core.models import Risk, ToolResult

_PRIMITIVES: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable[..., Any]
    risk: Risk = Risk.SAFE
    timeout: float = 30.0
    parameters: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.fn)

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _json_type(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if origin in (list, set, tuple):
            item = _json_type(args[0]) if args else {}
            return {"type": "array", "items": item}
        if origin is dict:
            return {"type": "object"}
        if len(args) == 1:  # Optional[X]
            return _json_type(args[0])
        return {}
    if isinstance(annotation, type) and annotation in _PRIMITIVES:
        return {"type": _PRIMITIVES[annotation]}
    if isinstance(annotation, type) and issubclass(annotation, str):
        return {"type": "string"}
    return {}


def build_parameters(fn: Callable[..., Any]) -> dict[str, Any]:
    """Derive a JSON Schema object from a function signature."""
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # unresolvable forward refs
        hints = {}
    props: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name.startswith("_") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        schema = _json_type(hints.get(name, param.annotation))
        props[name] = schema
        if param.default is inspect.Parameter.empty:
            required.append(name)
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


class ToolRegistry:
    """Holds tool specs and executes them with timeout + uniform results."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> ToolSpec:
        if spec.name in self._tools:
            raise ToolError("duplicate tool name", context={"name": spec.name})
        self._tools[spec.name] = spec
        return spec

    def tool(self, name: str | None = None, *, description: str = "",
             risk: Risk = Risk.SAFE, timeout: float = 30.0,
             tags: tuple[str, ...] = ()) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator registering a function as a tool."""

        def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(ToolSpec(
                name=name or fn.__name__,
                description=description or (inspect.getdoc(fn) or "").split("\n\n")[0],
                fn=fn,
                risk=risk,
                timeout=timeout,
                parameters=build_parameters(fn),
                tags=tags,
            ))
            return fn

        return wrap

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFound("no such tool", context={"name": name}) from None

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[n] for n in self.names()]

    def schemas(self, include: set[str] | None = None) -> list[dict[str, Any]]:
        return [s.to_openai_schema() for s in self.specs()
                if include is None or s.name in include]

    def validate(self, spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
        """Check required keys and drop unknown ones."""
        params = spec.parameters or {}
        props = params.get("properties", {})
        missing = [k for k in params.get("required", []) if k not in arguments]
        if missing:
            raise ToolValidationError("missing required arguments",
                                      context={"tool": spec.name, "missing": missing})
        return {k: v for k, v in arguments.items() if k in props} if props else dict(arguments)

    async def execute(self, name: str, arguments: dict[str, Any],
                      *, call_id: str | None = None) -> ToolResult:
        """Run a tool, never raising: failures come back as ``ToolResult``."""
        started = time.perf_counter()
        try:
            spec = self.get(name)
            args = self.validate(spec, arguments)
            if spec.is_async:
                coro = spec.fn(**args)
            else:
                coro = asyncio.to_thread(lambda: spec.fn(**args))
            output = await asyncio.wait_for(coro, timeout=spec.timeout)
            return ToolResult(tool=name, ok=True, output=output, call_id=call_id,
                              duration_ms=(time.perf_counter() - started) * 1000)
        except TimeoutError:
            err = ToolTimeout("tool timed out", context={"tool": name})
            return ToolResult(tool=name, ok=False, error=str(err), call_id=call_id,
                              duration_ms=(time.perf_counter() - started) * 1000)
        except Exception as exc:
            return ToolResult(tool=name, ok=False, error=f"{type(exc).__name__}: {exc}",
                              call_id=call_id,
                              duration_ms=(time.perf_counter() - started) * 1000)
