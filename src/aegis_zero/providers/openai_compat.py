"""OpenAI-compatible provider. Works with OpenAI, vLLM, LiteLLM, Ollama's
/v1 shim, and any local router exposing the same contract."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from ..core.errors import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from ..core.models import Completion, Message, ToolCall, Usage
from .base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001/v1",
        api_key: str = "",
        timeout: float = 120.0,
        client: Any = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = client
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        client = await self._http()
        try:
            resp = await client.post(
                f"{self.base_url}{path}", json=payload, headers=self._headers()
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeout("request timed out", context={"path": path}) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("transport failure", context={"path": path}) from exc

        if resp.status_code == 429:
            raise ProviderRateLimited("rate limited", context={"path": path})
        if resp.status_code >= 500:
            raise ProviderUnavailable("upstream error", context={"status": resp.status_code})
        if resp.status_code >= 400:
            raise ProviderError(
                "bad request", context={"status": resp.status_code, "body": resp.text[:300]}
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("non-JSON response") from exc

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> Completion:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_wire() for m in messages],
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = response_format

        started = time.perf_counter()
        body = await self._post("/chat/completions", payload)
        latency = (time.perf_counter() - started) * 1000

        choices = body.get("choices") or []
        if not choices:
            raise ProviderError("empty choices", context={"model": model})
        msg = choices[0].get("message") or {}
        usage_raw = body.get("usage") or {}

        return Completion(
            text=msg.get("content") or "",
            model=body.get("model", model),
            usage=Usage(
                int(usage_raw.get("prompt_tokens") or 0),
                int(usage_raw.get("completion_tokens") or 0),
            ),
            tool_calls=_parse_tool_calls(msg.get("tool_calls")),
            finish_reason=choices[0].get("finish_reason") or "stop",
            latency_ms=latency,
        )

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [m.to_wire() for m in messages],
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        client = await self._http()
        async with client.stream(
            "POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
        ) as resp:
            if resp.status_code >= 400:
                raise ProviderError("stream failed", context={"status": resp.status_code})
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk in ("", "[DONE]"):
                    if chunk == "[DONE]":
                        return
                    continue
                try:
                    delta = json.loads(chunk)["choices"][0]["delta"]
                except (ValueError, KeyError, IndexError):
                    continue
                piece = delta.get("content")
                if piece:
                    yield piece

    async def embed(self, texts: Sequence[str], *, model: str) -> list[list[float]]:
        body = await self._post("/embeddings", {"model": model, "input": list(texts)})
        rows = sorted(body.get("data") or [], key=lambda d: d.get("index", 0))
        return [list(r["embedding"]) for r in rows]

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


def _parse_tool_calls(raw: Any) -> tuple[ToolCall, ...]:
    if not raw:
        return ()
    calls: list[ToolCall] = []
    for item in raw:
        fn = item.get("function") or {}
        args = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"_raw": args}
        calls.append(
            ToolCall(
                name=fn.get("name", ""),
                arguments=args or {},
                id=item.get("id") or "call_unknown",
            )
        )
    return tuple(calls)
