# Legacy v1 modules

These are the original Aegis Zero modules, preserved for reference and for
migrating anything that still imports them. They are **not** installed by the
`aegis-zero` package and are not covered by CI.

| v1 module | v2 replacement |
|---|---|
| `puppeteer.py` | `aegis_zero.orchestrator.AgentEngine` |
| `agent_harness.py` | `aegis_zero.app.build_agent()` |
| `tool_policy.py` | `aegis_zero.tools.PolicyEngine` |
| `trusted_mcp.py` | `aegis_zero.tools` registry + policy |
| `memrl_engine.py` | `aegis_zero.memory.MemRLEngine` (async) |
| `context_engine.py` | `aegis_zero.orchestrator.ContextBuilder` |
| `aegis_config.py` | `aegis_zero.core.config.load_settings()` |

The v1 tests (`test_*.py` here) still pass against the v1 modules. Run them
with `python -m pytest legacy/` after installing `ollama` and `qdrant-client`.

New work should target the v2 API.
