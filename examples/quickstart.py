"""Minimal usage: ask a question, print the answer."""
import asyncio

from aegis_zero import build_agent
from aegis_zero.tools import ConsoleGate


async def main() -> None:
    async with build_agent(approval=ConsoleGate()) as agent:
        result = await agent.ask("What is 2^16, and why does it matter in computing?")
        print(result.answer)
        print("\nstats:", result.summary())


if __name__ == "__main__":
    asyncio.run(main())
