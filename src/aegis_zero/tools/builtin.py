"""A small, safe built-in toolset. Everything routes through the policy
engine, so these are deliberately narrow and side-effect explicit."""

from __future__ import annotations

import asyncio
import json
import math
from pathlib import Path
from typing import Any

from ..core.models import Risk
from .registry import ToolRegistry

MAX_READ_BYTES = 200_000


def register_builtins(registry: ToolRegistry, *, enable_http: bool = True) -> ToolRegistry:
    """Attach the default tools to a registry."""

    @registry.tool(risk=Risk.SAFE, description="Evaluate an arithmetic expression.")
    def calculate(expression: str) -> str:
        """Evaluate a arithmetic expression using a restricted namespace."""
        allowed: dict[str, Any] = {
            k: getattr(math, k)
            for k in (
                "sqrt",
                "pow",
                "log",
                "log10",
                "exp",
                "sin",
                "cos",
                "tan",
                "pi",
                "e",
                "floor",
                "ceil",
                "fabs",
            )
        }
        allowed.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum})
        if any(tok in expression for tok in ("__", "import", "open", "eval", "exec")):
            raise ValueError("expression contains forbidden tokens")
        result = eval(expression, {"__builtins__": {}}, allowed)
        return str(result)

    @registry.tool(risk=Risk.LOW, description="Read a UTF-8 text file.")
    async def read_file(path: str, max_bytes: int = MAX_READ_BYTES) -> str:
        """Read a text file from disk, truncated to ``max_bytes``."""
        p = Path(path).expanduser()

        def _read() -> str:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.read(max_bytes)

        return await asyncio.to_thread(_read)

    @registry.tool(risk=Risk.LOW, description="List entries in a directory.")
    async def list_dir(path: str = ".", limit: int = 200) -> list[str]:
        """List names in a directory, sorted, capped at ``limit``."""
        p = Path(path).expanduser()

        def _list() -> list[str]:
            return sorted(
                x.name + ("/" if x.is_dir() else "") for x in list(p.iterdir())[:limit]
            )

        return await asyncio.to_thread(_list)

    @registry.tool(risk=Risk.HIGH, description="Write text to a file.")
    async def write_file(path: str, content: str) -> str:
        """Write UTF-8 text to a file, creating parent directories."""
        p = Path(path).expanduser()

        def _write() -> str:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"wrote {len(content)} chars to {p}"

        return await asyncio.to_thread(_write)

    if enable_http:

        @registry.tool(
            risk=Risk.MEDIUM,
            timeout=30.0,
            description="HTTP GET a public URL and return the body.",
        )
        async def http_fetch(url: str, max_chars: int = 20_000) -> str:
            """Fetch a URL over HTTP(S) and return the truncated response body."""
            import httpx

            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as c:
                resp = await c.get(url, headers={"User-Agent": "AegisZero/2.0"})
                return f"HTTP {resp.status_code}\n{resp.text[:max_chars]}"

    @registry.tool(risk=Risk.SAFE, description="Pretty-print or validate JSON.")
    def format_json(text: str, indent: int = 2) -> str:
        """Parse and re-serialize JSON, raising on invalid input."""
        return json.dumps(json.loads(text), indent=indent, ensure_ascii=False)

    return registry


def default_registry(enable_http: bool = True) -> ToolRegistry:
    return register_builtins(ToolRegistry(), enable_http=enable_http)
