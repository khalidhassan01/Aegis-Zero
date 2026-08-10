# Architecture

## Design principles

**Everything is async.** Sub-agents that don't depend on each other run
concurrently. A dependency graph is resolved into waves; each wave executes in
parallel under a semaphore.

**Interception, not trust.** The model proposes tool calls; the policy engine
disposes. There is no path from a model output to a side effect that skips
policy evaluation.

**Typed failure.** Every error is a subclass of `AegisError` carrying
structured context and a `retryable` flag. Retry logic reads the flag rather
than pattern-matching on error strings.

**Events over hooks.** The engine publishes to a bus. Logging, metrics,
tracing, and UIs subscribe. Adding observability requires no engine changes.

**Composition over configuration.** `build_agent()` is a thin composition root.
Every component can be constructed and injected directly for testing.

## Execution pipeline

| Stage | Model | Purpose | Skipped when |
|---|---|---|---|
| Plan | fast | decompose into subtasks | goal is trivial or simple |
| Scout | fast | reconnaissance and constraints | goal is trivial or simple |
| Forge | deep | execute with a bounded tool loop | never |
| Synthesize | deep | merge subtask outputs | single subtask |
| Audit | fast | adversarial review | `enable_critique=False` |
| Revise | deep | correct issues the auditor found | audit passed |
| Learn | — | reward contributing memories | no memory configured |

### The Forge loop

Each subtask runs up to `max_tool_iterations` rounds of:

1. Call the model with the current message list and tool schemas.
2. If there are no tool calls, the text is the subtask result.
3. Otherwise, run every requested tool concurrently through policy.
4. Append results as `tool` messages and repeat.

If the iteration cap is reached, the model is asked once more with no tools for
a final answer — the loop cannot run away.

## Policy evaluation order

1. **Tool denylist** — configured `denied_tools` are refused outright.
2. **Rate limit** — per-run call caps.
3. **Argument guards** — URL, path, and command inspection. Any hit is a hard
   deny; these are not overridable by approval.
4. **Sanitization** — secret-looking keys and values are redacted.
5. **Risk threshold** — tools at or above the threshold require human approval.

Argument guards run before the risk threshold on purpose: a destructive command
is denied outright rather than presented to a human who might approve it by
reflex.

## MemRL

Utility is stored as an unbounded real score and squashed through a sigmoid for
ranking. Updates use a bandit-style rule:

```
score += learning_rate * (reward - tanh(score))
```

This is self-limiting — as `score` grows, `tanh(score)` approaches the reward
ceiling and further updates shrink, so a single memory cannot dominate.

Consolidation decays memories that were retrieved but never selected, then
prunes anything below `prune_below`.

## Concurrency and cancellation

`RunState` carries a `cancelled` flag checked at every budget checkpoint, so
cancellation is cooperative and leaves no partial side effects mid-tool.
Parallelism is bounded by `EngineConfig.max_parallel`.

## Extension points

| Extend | Subclass or pass |
|---|---|
| A new model backend | `providers.base.LLMProvider` |
| A new memory backend | `memory.store.VectorStore` |
| A new approval channel | `tools.approval.ApprovalGate` |
| New tools | `@registry.tool(...)` |
| New policy rules | `PolicyEngine(rules={...})` |
| New observability | `bus.subscribe(...)` |
