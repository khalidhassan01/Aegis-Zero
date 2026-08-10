"""Register your own tools. Schemas are derived from type hints."""
import asyncio

from aegis_zero import build_agent
from aegis_zero.core.models import Risk
from aegis_zero.tools import AutoApprove, default_registry

registry = default_registry()


@registry.tool(risk=Risk.SAFE)
async def get_weather(city: str, units: str = "celsius") -> str:
    """Return the current weather for a city."""
    return f"22 degrees {units} and clear in {city}"


@registry.tool(risk=Risk.MEDIUM)
def query_database(sql: str, limit: int = 100) -> list[dict]:
    """Run a read-only query against the application database."""
    return [{"id": 1, "name": "example"}][:limit]


async def main() -> None:
    async with build_agent(registry=registry, approval=AutoApprove()) as agent:
        print(await (await agent.ask("What is the weather in Rabat?")).answer)


if __name__ == "__main__":
    asyncio.run(main())
