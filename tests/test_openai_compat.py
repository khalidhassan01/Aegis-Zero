"""Transport-level tests for the OpenAI-compatible provider, using a fake
httpx client so no network is touched."""
from __future__ import annotations

import json

import httpx
import pytest

from aegis_zero.core.errors import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from aegis_zero.core.models import Message
from aegis_zero.providers.openai_compat import OpenAICompatProvider

MSGS = [Message(role="user", content="hi")]


def provider_with(handler) -> OpenAICompatProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return OpenAICompatProvider(base_url="http://test/v1", api_key="k",
                                client=client)


def chat_body(content="hello", tool_calls=None, model="m"):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {"model": model, "choices": [{"message": msg, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4}}


async def test_completion_is_parsed():
    p = provider_with(lambda r: httpx.Response(200, json=chat_body()))
    out = await p.complete(MSGS, model="m")
    assert out.text == "hello"
    assert out.usage.total_tokens == 7
    assert out.latency_ms >= 0


async def test_authorization_header_is_sent():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=chat_body())

    await provider_with(handler).complete(MSGS, model="m")
    assert seen["auth"] == "Bearer k"


async def test_tools_are_forwarded_in_payload():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=chat_body())

    schema = [{"type": "function", "function": {"name": "f", "parameters": {}}}]
    await provider_with(handler).complete(MSGS, model="m", tools=schema)
    assert seen["body"]["tools"] == schema
    assert seen["body"]["tool_choice"] == "auto"


async def test_tool_calls_are_parsed_from_response():
    body = chat_body(content="", tool_calls=[
        {"id": "c1", "type": "function",
         "function": {"name": "calc", "arguments": '{"x": 2}'}}
    ])
    p = provider_with(lambda r: httpx.Response(200, json=body))
    out = await p.complete(MSGS, model="m")
    assert out.tool_calls[0].name == "calc"
    assert out.tool_calls[0].arguments == {"x": 2}


@pytest.mark.parametrize("status,exc", [
    (429, ProviderRateLimited),
    (500, ProviderUnavailable),
    (503, ProviderUnavailable),
    (400, ProviderError),
    (404, ProviderError),
])
async def test_status_codes_map_to_typed_errors(status, exc):
    p = provider_with(lambda r: httpx.Response(status, json={"e": 1}))
    with pytest.raises(exc):
        await p.complete(MSGS, model="m")


async def test_retryable_flags_are_correct():
    p = provider_with(lambda r: httpx.Response(429))
    with pytest.raises(ProviderRateLimited) as e:
        await p.complete(MSGS, model="m")
    assert e.value.retryable is True

    p2 = provider_with(lambda r: httpx.Response(400))
    with pytest.raises(ProviderError) as e2:
        await p2.complete(MSGS, model="m")
    assert e2.value.retryable is False


async def test_timeout_maps_to_provider_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeout):
        await provider_with(handler).complete(MSGS, model="m")


async def test_transport_error_maps_to_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable):
        await provider_with(handler).complete(MSGS, model="m")


async def test_non_json_response_is_an_error():
    p = provider_with(lambda r: httpx.Response(200, text="<html>oops"))
    with pytest.raises(ProviderError):
        await p.complete(MSGS, model="m")


async def test_empty_choices_is_an_error():
    p = provider_with(lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(ProviderError):
        await p.complete(MSGS, model="m")


async def test_embeddings_preserve_input_order():
    body = {"data": [{"index": 1, "embedding": [0.2]},
                     {"index": 0, "embedding": [0.1]}]}
    p = provider_with(lambda r: httpx.Response(200, json=body))
    assert await p.embed(["a", "b"], model="e") == [[0.1], [0.2]]


async def test_streaming_yields_deltas():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n'
        'data: garbage-not-json\n'
        'data: [DONE]\n'
    )
    p = provider_with(lambda r: httpx.Response(200, text=sse))
    chunks = [c async for c in p.stream(MSGS, model="m")]
    assert "".join(chunks) == "Hello"
