# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [2.0.0] - 2026-08-10

Complete architectural rebuild. v1 modules are preserved under `legacy/`.

### Added

- **Async runtime.** The entire execution path is `async`. Independent
  subtasks are resolved into dependency waves and run concurrently.
- **Provider abstraction** (`providers/`). Any OpenAI-compatible endpoint —
  OpenAI, Ollama, vLLM, LiteLLM, or a local router. Includes retry with
  exponential backoff and jitter, an ordered model fallback chain, streaming,
  and embeddings.
- **`EchoProvider`** for deterministic, offline, no-network testing.
- **Tool registry** with JSON Schemas derived from type hints, so the model's
  contract cannot drift from the implementation. Per-tool timeouts; tool
  failures return a typed result rather than raising.
- **Policy engine** (`tools/policy.py`) with four-way decisions
  (allow / sanitize / approve / deny), risk tiers, per-run call limits,
  DNS-resolving SSRF protection, symlink-aware path containment, destructive
  command detection, and nested secret redaction.
- **Approval gates**: `ConsoleGate`, `CallbackGate`, `AutoApprove`, `DenyAll`.
  The default is `DenyAll` — risky tools do not run without a configured human.
- **MemRL** rewritten as an async reinforcement-weighted retriever. Ranking
  blends similarity, learned utility, and recency; consolidation decays and
  prunes memories that never help.
- **Pluggable vector stores**: dependency-free `InMemoryStore` and an optional
  `QdrantStore`.
- **Event bus** with typed events; logging, metrics, and JSONL tracing are
  subscribers rather than engine concerns.
- **Budgets** for steps, tokens, wall-clock time, tool calls, and tool-loop
  iterations, plus cooperative cancellation.
- **Typed error taxonomy** rooted at `AegisError`, each carrying structured
  context and a `retryable` flag.
- **Layered configuration**: defaults < YAML < environment.
- **CLI**: `aegis run | tools | config | health`.
- **CI**: ruff, mypy, pytest on Python 3.11/3.12/3.13, a coverage floor,
  a distribution build, an installed-CLI smoke test, and CodeQL.
- 179 tests at 86% coverage; four runnable examples.

### Changed

- Repository restructured to a `src/` layout installable as `aegis-zero`.
- `Puppeteer` → `AgentEngine`; `ToolPolicy` → `PolicyEngine`;
  `ContextEngine` → `ContextBuilder`; `aegis_config.get_*()` →
  `load_settings()`.
- The auditor now returns structured JSON. Unparseable auditor output is
  treated as `revise` with low confidence instead of a silent pass.
- Sub-agent prompts are versioned constants rather than inline strings.

### Fixed

- **Path containment bypass.** `/proc/self/environ` resolved to
  `/proc/<pid>/environ`, slipping past the prefix denylist. Both the pre- and
  post-resolution path are now checked.
- **Tool-call wire format.** `arguments` was serialized as a JSON object;
  the OpenAI contract requires a JSON *string*, and Ollama and vLLM reject an
  object with HTTP 400. Found by running against a live model.
- **Secret-redaction false positives.** `tokens`, `max_tokens`, and other
  telemetry keys matched the `token` secret pattern and were redacted from
  metrics output. Key matching is now whole-word with a safe-key allowlist.
- Silent `except: pass` blocks removed; failures are typed or explicitly
  suppressed with a stated reason.
- Removed the dead `unittest2` dependency.

### Removed

- Duplicate `README-1.md` and six generated HTML documents (moved to
  `docs/assets/`).
- Self-referential verification and audit reports (moved to `docs/`).

## [1.0.0] - 2026-08

- Initial release: 12-factor agent design, Puppeteer orchestration,
  MemRL engine, tool policy layer, trusted MCP adapter.
