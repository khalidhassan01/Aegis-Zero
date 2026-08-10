# Aegis Zero

**A state-of-the-art agentic runtime.** Async orchestration, policy-governed
tool use, and reinforcement-weighted memory — in a single dependency-light
Python package.

[![CI](https://github.com/khalidhassan01/Aegis-Zero/actions/workflows/ci.yml/badge.svg)](https://github.com/khalidhassan01/Aegis-Zero/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## Why Aegis Zero

Most agent frameworks give you a prompt loop and hope for the best. Aegis Zero
is built around three commitments:

1. **Nothing executes unreviewed.** Every tool call passes a policy engine that
   classifies risk, blocks SSRF and destructive commands, contains filesystem
   access, redacts secrets, and routes high-risk actions to a human.
2. **Memory learns.** Retrieved memories are scored by whether they actually
   helped. Useful recollections surface more often; misleading ones decay away.
3. **Failures are typed, never swallowed.** Every error is a specific exception
   with structured context. Budgets are hard limits, not suggestions.

## Install

```bash
pip install -e ".[dev]"          # from a clone
pip install -e ".[qdrant]"       # with the Qdrant memory backend
```

Requires Python 3.11+. Runtime dependencies are just `httpx` and `PyYAML`.

## Quick start

```python
import asyncio
from aegis_zero import build_agent
from aegis_zero.tools import ConsoleGate

async def main():
    async with build_agent(approval=ConsoleGate()) as agent:
        result = await agent.ask("What is 2^16, and why does it matter?")
        print(result.answer)
        print(result.summary())

asyncio.run(main())
```

From the command line:

```bash
aegis run "Summarise the CAP theorem"     # run a goal
aegis run "..." --stats -v                # with metrics and live events
aegis tools                               # list tools + policy verdicts
aegis config                              # show effective configuration
aegis health                              # check provider and memory
```

## Architecture

```
                        ┌─────────────┐
   goal ───────────────>│   Planner   │  decompose into subtasks
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │    Scout    │  reconnaissance (complex goals only)
                        └──────┬──────┘
                               │
              ┌────────────────┼────────────────┐   parallel dependency waves
        ┌─────▼─────┐    ┌─────▼─────┐    ┌─────▼─────┐
        │   Forge   │    │   Forge   │    │   Forge   │  bounded tool loops
        └─────┬─────┘    └─────┬─────┘    └─────┬─────┘
              └────────────────┼────────────────┘
                        ┌──────▼──────┐
                        │ Synthesizer │  merge, resolve conflicts
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │   Auditor   │  adversarial review ──┐
                        └──────┬──────┘                       │ revise
                               │  pass                        │
                        ┌──────▼──────┐                       │
                        │   MemRL     │<──────────────────────┘
                        └─────────────┘  reward what helped
```

Every tool call in every Forge loop is intercepted:

```
tool call ──> PolicyEngine ──> allow ─────────────> execute
                    │
                    ├────────> sanitize ──────────> execute (redacted args)
                    ├────────> approve ──> human ─> execute or refuse
                    └────────> deny ─────────────> error returned to model
```

### Package layout

```
src/aegis_zero/
├── core/            models, typed errors, layered config, event bus
├── providers/       async LLM abstraction, OpenAI-compat, retry + fallback
├── tools/           registry with derived schemas, policy engine, approvals
├── memory/          vector stores, MemRL reinforcement retrieval
├── orchestrator/    planning, context assembly, the agent engine
├── observability/   structured logging, metrics, JSONL tracing
├── app.py           composition root
└── cli.py           command-line interface
```

## Core concepts

### Tools are typed functions

Schemas are derived from signatures, so the contract can't drift from the code.

```python
from aegis_zero.core.models import Risk
from aegis_zero.tools import default_registry

registry = default_registry()

@registry.tool(risk=Risk.MEDIUM)
async def query_database(sql: str, limit: int = 100) -> list[dict]:
    """Run a read-only query against the application database."""
    return await db.fetch(sql, limit)
```

### Policy is declarative and enforced

```python
from aegis_zero.tools import PolicyEngine

policy = PolicyEngine(
    approval_threshold="high",       # high and critical need a human
    allowed_roots=("/srv/workspace",),  # filesystem containment
    denied_tools=("shell",),
    allow_network=True,
)
```

Blocked by default: private/loopback/metadata addresses after DNS resolution,
non-HTTP schemes, `/etc/shadow` and friends, `.ssh` and `.gnupg`, symlink and
traversal escapes from allowed roots, and a broad set of destructive shell
patterns. Secret-looking keys and values are redacted before a tool ever sees
them — and before anything reaches a log or trace.

### Memory that learns

```python
result = await agent.ask("How do I deploy the service?")
# Memories used in a successful, confidently-audited run get rewarded.
# Memories that were retrieved but never helped decay and are eventually pruned.

await agent.memory.consolidate()   # nightly maintenance
await agent.memory.health()        # {'count': ..., 'hit_rate': ..., ...}
```

Ranking blends similarity, learned utility, and recency:

```
rank = 0.60 * similarity + 0.30 * utility + 0.10 * recency
```

### Budgets are enforced

```python
from aegis_zero.core.models import Budget

result = await agent.ask(goal, budget=Budget(
    max_steps=12, max_tokens=50_000, max_seconds=120, max_tool_calls=20,
))
```

Exceeding any limit raises `BudgetExceeded`, which the engine converts into a
failed-but-reported result rather than an unbounded spend.

### Observability

```python
agent.bus.subscribe(lambda e: print(e.type.value, e.data))
print(agent.metrics.snapshot())
# {'runs': 3, 'llm_calls': 14, 'tool_calls': 6, 'tool_failures': 0,
#  'policy_denials': 1, 'tokens': 8420, 'latency_p95_ms': 812.4, ...}
```

Set `trace_dir` in config to write a JSONL trace of every event.

## Configuration

Defaults < YAML file < environment. Environment always wins.

```bash
export AEGIS_PROVIDER__BASE_URL=http://127.0.0.1:11434/v1
export AEGIS_MODELS__FAST=qwen2.5:7b
export AEGIS_POLICY__APPROVAL_THRESHOLD=medium
export AEGIS_MAX_STEPS=12
```

See [`aegis.example.yaml`](aegis.example.yaml) for every option.

Any OpenAI-compatible endpoint works: OpenAI, Ollama's `/v1` shim, vLLM,
LiteLLM, or a local router.

## Testing without a model

`EchoProvider` returns scripted completions, so orchestration logic is testable
offline and deterministically:

```python
from aegis_zero.providers import EchoProvider, scripted_tool_call

provider = EchoProvider(script=[
    scripted_tool_call("calculate", {"expression": "6*7"}),
    "The answer is 42.",
    '{"verdict":"pass","confidence":0.95,"issues":[]}',
])
```

See [`examples/offline_testing.py`](examples/offline_testing.py).

## Development

```bash
pytest --cov              # 167 tests
ruff check src tests      # lint
mypy                      # type check
```

CI runs lint, mypy, tests on Python 3.11/3.12/3.13, a coverage floor, a
distribution build, an installed-CLI smoke test, and CodeQL.

## Migrating from v1

v1 modules are preserved under [`legacy/`](legacy/) for reference. The mapping:

| v1 | v2 |
|---|---|
| `puppeteer.Puppeteer` | `orchestrator.AgentEngine` |
| `agent_harness.HardenedPuppeteer` | `app.build_agent()` |
| `tool_policy.ToolPolicy` | `tools.PolicyEngine` |
| `memrl_engine.MemRLEngine` | `memory.MemRLEngine` (async) |
| `context_engine.ContextEngine` | `orchestrator.ContextBuilder` |
| `aegis_config.get_*()` | `core.config.load_settings()` |
| direct `ollama` calls | `providers.OpenAICompatProvider` |

The principal change is that everything is `async`, and subtasks that don't
depend on each other now run concurrently.

## License

MIT — see [LICENSE](LICENSE).
