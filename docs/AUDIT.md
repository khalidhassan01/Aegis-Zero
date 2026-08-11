# Architecture Audit — Aegis Zero v2.0.0

Method: every defect below was reproduced with an executable probe before
being reported, and each fix is pinned by a regression test. Findings I
could not reproduce are listed under *Hypotheses that did not hold*, because
a wrong prediction is as informative as a confirmed one.

Probes live in `tests/test_audit_regressions.py` and
`tests/test_memrl_dynamics.py`.

---

## Summary

| # | Defect | Severity | Status |
|---|---|---|---|
| 1 | Duplicate subtask id silently deletes a subtask | High | Fixed |
| 2 | Dependency on a non-existent task treated as satisfied | Medium | Fixed |
| 3 | Self-dependency accepted | Low | Fixed |
| 4 | Cycle broken non-deterministically | Medium | Fixed |
| 5 | Context token budget not enforced (40x overrun) | **Critical** | Fixed |
| 6 | Oversized single message bypasses trimming | High | Fixed |
| 7 | NUL byte in a path crashes policy evaluation | High | Fixed |
| 8 | Percent-encoded traversal skips path checks | Medium | Fixed |
| 9 | `fail` verdict never triggers a revision | Medium | Fixed |
| 10 | Winner-take-all memory retrieval | High | Fixed |
| 11 | Command denylist defeated by trivial obfuscation | **Critical** | Documented, not fixed |
| 12 | `stream()` bypasses retry and fallback | Medium | Fixed |
| 13 | No context-window awareness per model | High | Fixed |
| 14 | Coarse memory credit assignment | Medium | Open |

---

## 1-4. Plan graph handling

`_topological_waves` keyed a dict on planner-supplied ids:

```python
pending = {t.id: t for t in subtasks}
```

An LLM planner emitting the same id twice caused one subtask to disappear
before execution. No error, no warning — the work was simply never done and
the synthesizer merged an incomplete result set.

Probe result: two subtasks in, **one** out.

The dependency test `all(d in done or d not in pending for d in t.depends_on)`
also treated a dependency on a task that never existed as already satisfied,
so a typo in a plan silently reordered execution.

**Fixed** by `normalize_subtasks()`: ids are made unique, unknown and
self-referential dependencies are dropped, and cycles break on the lowest id
so execution is reproducible.

## 5-6. Context budget was advisory

The most serious functional defect. `ContextBuilder` advertised a hard token
budget; `_trim` did not enforce one.

| Requested budget | Delivered |
|---|---|
| 100 tokens | 4012 tokens |
| 10 tokens | 6012 tokens |

Two causes: `keep_recent` was applied as a floor that ignored the budget
entirely, and a single oversized message was passed through whole because
the loop only ever *skipped* messages, never truncated them.

In production this silently exceeds the model's context window, and the
provider rejects the request — the failure surfaces far from its cause.

**Fixed.** A single newest-first pass now enforces the budget, oversized
messages are truncated with an explicit `[... truncated ...]` marker, and
elision is always announced so the model is not misled into believing it saw
the full conversation. Verified: 100-token budget now yields exactly 100.

## 7-8. Policy engine input handling

`check_path("/tmp/ok\0/etc/shadow")` raised an unhandled `ValueError` from
`Path.resolve()`, propagating out of policy evaluation and aborting the run —
a denial of service reachable from any model-proposed tool argument.

**Fixed:** NUL bytes are rejected explicitly, percent-encoding is decoded
before the path checks, and `ValueError` is caught alongside `OSError`.

## 9. The `fail` verdict was never revised

```python
while revisions < max_revisions and not critique.passed and critique.verdict != "fail":
```

The strongest signal that an answer is wrong was the one signal that
guaranteed no correction attempt.

This one is arguably a design choice rather than a bug — "fail" can
reasonably mean *unsalvageable, stop*. It is now an **explicit** policy
instead of an accident: `revise_on_fail` (default `True`) with
`max_fail_revisions` capping it at one attempt, so a harsh verdict cannot
consume the whole revision budget.

## 10. Winner-take-all memory retrieval

Ranking was greedy — `0.60·similarity + 0.30·utility + 0.10·recency`. A
memory that won once gained utility, so it was retrieved again, so it gained
more utility.

Experiment: two memories with identical similarity, one given a single `+1`
reward, then 15 recalls.

| | Before | After |
|---|---|---|
| Lucky memory's share | **15/15** | 8/15 |

A genuinely better alternative could never be discovered. **Fixed** with a
UCB1-style exploration bonus, capped so novelty cannot outrank strong
relevance, and disableable via `exploration=0.0`.

---

## 11. Command denylist is not a security boundary

**This is the most important finding in the audit and it is not fixed,
because it cannot be fixed by patching the regex.**

`SECURITY_MODEL.md` claims destructive commands are blocked. The denylist
catches the literal forms and misses trivial obfuscations:

| Payload | Result |
|---|---|
| `rm -rf /` | blocked |
| `r''m -rf /` | **allowed** |
| `echo cm0gLXJmIC8= \| base64 -d \| sh` | **allowed** |

A shell has unbounded ways to express the same command, so enumerating bad
strings cannot work. The honest options are containment (run tools in a
sandbox with no access to what must not be destroyed) or an allowlist of
permitted commands. The documentation has been corrected to stop claiming a
guarantee the code does not provide.

The SSRF defences, by contrast, held against every probe: decimal, hex, and
octal encoded addresses, IPv6 loopback, IPv6-mapped IPv4, userinfo tricks,
and trailing-dot DNS were all blocked, because they resolve the host and
check the resulting address rather than pattern-matching the string.

## 12-14. Open items

- **`stream()` bypasses `ResilientProvider`** — **Fixed.** Streaming now
  retries before the first token and falls back down the model chain like
  `complete()` (see `tests/test_streaming_resilience.py`).
- **No per-model context window.** `max_tokens` was one global number, so the
  budget was wrong for every model that was not the one it was tuned for.
  **Fixed** by `ModelSettings.context_windows` + a per-model prompt budget
  resolved in `ContextBuilder` (P5, audit #13).
- **Coarse credit assignment.** Every memory retrieved during a successful
  run receives an identical reward, including memories that were irrelevant.
  Fixing this needs per-memory attribution, which the engine does not track.
  Still open (P6).

---

## Hypotheses that did not hold

Recorded because they constrain the design and should not be re-litigated.

**Tool-budget race.** I expected `state.tool_calls += 1` followed by a
comparison, across `asyncio.gather`, to be a check-then-act race admitting
more executions than the budget. It is not: asyncio runs coroutines on a
single thread and neither statement awaits between them, so the sequence is
atomic. A 10-call batch against a budget of 2 executed exactly 2.

**Unbounded utility growth.** I expected `score += lr·(reward − tanh(score))`
to grow without limit under repeated reward. It saturates: 500 consecutive
`+1` rewards reach 2.64, and roughly 10 negative rewards reverse a memory
that had won 50 times. The rule is sound and self-limiting.

**Percent-encoded traversal reaching `/etc/shadow`.** My probe reported a
bypass, but the path resolved relative to the working directory and never
pointed at a protected file. Re-running from `/` confirmed both the encoded
and plain forms are blocked. The probe was a false positive; the decode step
was added anyway, since relying on the working directory is fragile.
