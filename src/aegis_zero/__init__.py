"""Aegis Zero - a state-of-the-art agentic runtime.

    import asyncio
    from aegis_zero import build_agent

    async def main():
        async with build_agent() as agent:
            result = await agent.ask("What is the capital of Morocco?")
            print(result.answer)

    asyncio.run(main())
"""
from __future__ import annotations

__version__ = "2.0.0"

from .app import Aegis, build_agent
from .core.config import Settings, load_settings
from .core.errors import AegisError
from .core.models import Budget, Message, Risk
from .orchestrator import AgentEngine, AgentResult, EngineConfig
from .providers import EchoProvider, LLMProvider, build_provider
from .tools import ApprovalGate, AutoApprove, ConsoleGate, PolicyEngine, ToolRegistry

__all__ = [
    "Aegis",
    "AegisError",
    "AgentEngine",
    "AgentResult",
    "ApprovalGate",
    "AutoApprove",
    "Budget",
    "ConsoleGate",
    "EchoProvider",
    "EngineConfig",
    "LLMProvider",
    "Message",
    "PolicyEngine",
    "Risk",
    "Settings",
    "ToolRegistry",
    "__version__",
    "build_agent",
    "build_provider",
    "load_settings",
]
