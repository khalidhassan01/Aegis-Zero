"""Subscribe to the event bus to build a live UI or audit log."""

import asyncio

from aegis_zero import build_agent
from aegis_zero.core.events import EventType
from aegis_zero.tools import AutoApprove


async def main() -> None:
    agent = build_agent(approval=AutoApprove())

    def on_event(event) -> None:
        if event.type is EventType.TOOL_START:
            print(f"  -> calling {event.data['tool']}")
        elif event.type is EventType.TOOL_END:
            print(f"  <- {event.data['tool']} ok={event.data['ok']}")
        elif event.type is EventType.POLICY_DECISION:
            print(f"  !! policy {event.data['decision']} on {event.data['tool']}")

    agent.bus.subscribe(on_event)

    async with agent:
        result = await agent.ask("Compute 17 factorial and explain the growth rate.")
        print("\n" + result.answer)
        print("\nmetrics:", agent.metrics.snapshot())


if __name__ == "__main__":
    asyncio.run(main())
