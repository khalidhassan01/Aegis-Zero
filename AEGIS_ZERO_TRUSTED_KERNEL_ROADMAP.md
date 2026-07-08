# Aegis Zero Trusted Kernel Roadmap

## Purpose

This roadmap converts the current hardening work into an implementation order for a real trusted local agent kernel.

The target is not "more features." The target is:

- one secure execution path,
- one trusted retrieval boundary,
- one policy-enforced tool layer,
- one testable orchestration loop.

## Current Status

Implemented in this workspace:

- local `ContextEngine` and `MemoryWriter`
- trusted MCP read adapter
- centralized tool policy
- policy-enforced tool execution path in the harness
- semantic-cache trust gating
- unit tests for policy and trusted retrieval boundary

Current proof points:

- `python3 -m py_compile tool_policy.py trusted_mcp.py context_engine.py puppeteer.py agent_harness.py test_policy_and_adapter.py`
- `python3 -m unittest -v test_policy_and_adapter.py`

## Build Goal

Deliver `Aegis Zero v0: Trusted Local Agent Kernel`.

Definition of done:

1. All tool access flows through deterministic policy and audit logging.
2. All retrieval shown to models is normalized and trust-labeled.
3. High-risk actions require approval through one central path.
4. The agent loop has regression tests for safety and basic capability.
5. No critical runtime dependency is imported from out-of-repo absolute paths.

## Workstreams

### 1. Tool Execution Unification

Goal:

- remove remaining direct tool calls outside trusted execution paths.

Tasks:

- route all future write/network/exec actions through `HardenedPuppeteer.execute_tool()`
- add wrapper helpers for common tool categories:
  - `execute_read_tool`
  - `execute_write_tool`
  - `execute_network_tool`
  - `execute_exec_tool`
- add structured audit records for every tool decision and tool result

Files:

- [agent_harness.py](/home/khalid/Dokumente/Aegis-Zero/agent_harness.py)
- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py)
- [tool_policy.py](/home/khalid/Dokumente/Aegis-Zero/tool_policy.py)

### 2. Policy Expansion

Goal:

- turn `ToolPolicy` into a real execution safety layer, not just a starter policy table.

Tasks:

- add explicit rule coverage for:
  - file read
  - file write
  - shell exec
  - HTTP/network fetch
  - memory/vector-store write
- add argument validators for:
  - filesystem paths
  - URL hosts and schemes
  - shell command deny patterns
  - payload size limits
- add collection/path allowlists from config

Files:

- [tool_policy.py](/home/khalid/Dokumente/Aegis-Zero/tool_policy.py)
- [aegis.conf.yaml.txt](/home/khalid/Dokumente/Aegis-Zero/aegis.conf.yaml.txt)

### 3. Trusted Retrieval Consolidation

Goal:

- ensure all model-visible external context is mediated by one trusted adapter.

Tasks:

- move any future search/cache/document adapters into `trusted_mcp.py`
- add provenance fields:
  - `source`
  - `trust_level`
  - `retrieved_at`
  - `review_status`
- add prompt-injection test corpus for retrieved content
- add maximum token/character budget enforcement before prompt rendering

Files:

- [trusted_mcp.py](/home/khalid/Dokumente/Aegis-Zero/trusted_mcp.py)
- [context_engine.py](/home/khalid/Dokumente/Aegis-Zero/context_engine.py)
- [test_policy_and_adapter.py](/home/khalid/Dokumente/Aegis-Zero/test_policy_and_adapter.py)

### 4. Approval Flow Integration

Goal:

- centralize irreversible and approval-required actions under one auditable path.

Tasks:

- make `requires_approval` decisions visible in tool-level traces
- add tests for:
  - approval granted
  - approval rejected
  - approval transport unavailable
- standardize the irreversible-action classification

Files:

- [agent_harness.py](/home/khalid/Dokumente/Aegis-Zero/agent_harness.py)
- [test_policy_and_adapter.py](/home/khalid/Dokumente/Aegis-Zero/test_policy_and_adapter.py)

### 5. Runtime Configuration Cleanup

Goal:

- remove hardcoded runtime assumptions from the remaining modules.

Tasks:

- replace fixed Qdrant host/port values with config/env-backed values in:
  - `agent_harness.py`
  - `memrl_engine.py`
- centralize environment access in one small config helper
- define safe defaults for:
  - Qdrant host/port
  - embedding model
  - cache thresholds
  - approval settings

Files:

- [agent_harness.py](/home/khalid/Dokumente/Aegis-Zero/agent_harness.py)
- [memrl_engine.py](/home/khalid/Dokumente/Aegis-Zero/memrl_engine.py)
- [context_engine.py](/home/khalid/Dokumente/Aegis-Zero/context_engine.py)

### 6. Safety and Regression Testing

Goal:

- prove the trusted kernel stays safe while capability evolves.

Tasks:

- keep `test_policy_and_adapter.py` as the boundary test suite
- add:
  - `test_harness_tools.py`
  - `test_prompt_injection_samples.py`
  - `test_cache_trust_rules.py`
- create test fixtures for:
  - malicious retrieved text
  - untrusted cache metadata
  - blocked URLs
  - blocked shell commands
  - approval-required write actions

Files:

- [test_policy_and_adapter.py](/home/khalid/Dokumente/Aegis-Zero/test_policy_and_adapter.py)

### 7. Orchestration Simplification

Goal:

- reduce architectural surface area until the trusted kernel is stable.

Tasks:

- keep Scout/Forge/Auditor, but treat multi-agent as optional
- prefer single-path execution for ordinary tasks
- avoid adding new autonomous loops before tool policy and tests are broader
- defer ambitious self-improvement wiring until outcome labeling and evaluation exist

Files:

- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py)
- [memrl_engine.py](/home/khalid/Dokumente/Aegis-Zero/memrl_engine.py)

## Recommended Execution Order

### Milestone 1: Trusted Boundary Complete

- finish policy expansion
- finish config cleanup
- remove remaining hardcoded runtime assumptions
- add approval-path tests and transport-failure tests

Exit criteria:

- every tool category used by the repo has a policy rule
- no critical path imports external absolute runtime modules
- safety tests pass locally

### Milestone 2: Trusted Kernel Runnable

- wire one end-to-end path:
  - classify
  - retrieve through trusted adapter
  - reason
  - optionally audit
  - execute tool through policy
  - checkpoint and observe

Exit criteria:

- one fully local happy path runs without hidden external code dependencies
- denied and approval-required actions behave deterministically

### Milestone 3: Safety Regression Pack

- expand test coverage
- add malicious retrieval fixtures
- add harness-level execution tests

Exit criteria:

- policy and trusted-boundary regressions are caught automatically

### Milestone 4: Capability Expansion

- only after the trusted kernel is stable:
  - broader tool adapters
  - richer context assembly
  - better memory logic
  - measured multi-agent use

## What Not To Do Yet

- do not add unrestricted web autonomy
- do not add new self-improvement loops without evaluation
- do not trust LLM self-auditing as the main safety boundary
- do not add more architecture layers until tool policy and tests cover the current ones

## Next Concrete Implementation Step

The best immediate coding task is:

`Milestone 1 / Runtime Configuration Cleanup`

Reason:

- it removes remaining hardcoded runtime fragility,
- improves reproducibility,
- and reduces the chance that safety logic is bypassed by environment mismatch.

After that:

- expand harness tests,
- then wire the first fully local trusted-kernel execution path.
