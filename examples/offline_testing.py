"""Test agent logic deterministically with no model server."""

import asyncio

from aegis_zero.orchestrator import AgentEngine, EngineConfig
from aegis_zero.providers import EchoProvider, scripted_tool_call
from aegis_zero.tools import AutoApprove, default_registry


async def main() -> None:
    provider = EchoProvider(
        script=[
            scripted_tool_call("calculate", {"expression": "6*7"}),
            "The answer is 42.",
            '{"verdict":"pass","confidence":0.95,"issues":[]}',
        ]
    )
    engine = AgentEngine(
        provider,
        registry=default_registry(),
        approval=AutoApprove(),
        config=EngineConfig(fast_model="f", deep_model="d"),
    )
    result = await engine.run("What is six times seven?")
    assert result.answer == "The answer is 42."
    assert result.tool_results[0].output == "42"
    print("deterministic run passed:", result.summary())


if __name__ == "__main__":
    asyncio.run(main())
