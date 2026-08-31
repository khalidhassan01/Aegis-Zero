# Roadmap — bringing Aegis Zero to the current state of the art

Every recommendation carries a citation whose arXiv ID was resolved against
the arXiv API before inclusion; the titles were checked to match the claim.
Where the evidence is a vendor blog rather than a peer-reviewed result, it
says so. Where I measured something on this codebase, the number is here.

The ordering is by expected value, not by novelty. Several fashionable
techniques are in *Deliberately not doing* with the reason.

---

## The single most important finding

**Aegis Zero's Auditor→Revise loop is intrinsic self-correction, and the
evidence says that does not work.**

> "LLMs struggle to self-correct their responses without external feedback,
> and at times, their performance even degrades."
> — Huang et al., *Large Language Models Cannot Self-Correct Reasoning Yet*,
> ICLR 2024 (peer-reviewed), arXiv:2310.01798

The current loop asks a model to grade another model's answer with no
external signal, then asks for a revision based on that grade. That is the
exact configuration the paper finds neutral-to-harmful. It also costs two
extra LLM calls per run.

This does not mean "delete the auditor". It means the auditor must be
**grounded in something outside the model**. The fix is P1 below.

---

## P0 — Correctness and honesty (done)

Completed during the audit; documented in `AUDIT.md`.

| Fix | Evidence it was needed |
|---|---|
| Enforce the context budget | measured 40x overrun (100 → 4012 tokens) |
| Unique subtask ids | duplicate id deleted an entire subtask |
| Reject NUL bytes in paths | unhandled `ValueError` aborted the run |
| Exploration in memory ranking | one lucky reward won 15/15 retrievals |
| Retry/fallback for `stream()` | streaming had no resilience at all |
| Stop claiming the shell denylist is a boundary | `r''m -rf /` bypasses it |

---

## P1 — Ground the Auditor in external verification  *(complexity: M)*

Replace "does the model think this is good" with "did it pass a check the
model cannot talk its way around".

```
Verifier protocol:
  - schema/format validation      (JSON parses, required fields present)
  - execution                     (code runs, tests pass, exit code 0)
  - arithmetic recomputation      (recompute claimed numbers)
  - citation grounding            (quoted spans exist in a retrieved source)
  - tool-result consistency       (claims match what tools returned)
```

Revise **only** when a verifier fails, and pass the concrete failure to the
reviser rather than prose criticism. Where no verifier applies, skip
critique and say so in the result instead of burning two calls on a ritual.

- Reflexion's gains come from an external evaluator, not introspection —
  Shinn et al., NeurIPS 2023, arXiv:2303.11366
- Naive self-refinement loops: Madaan et al., arXiv:2303.17651, with the
  negative result above as the controlling evidence

**Expected effect:** fewer tokens, and revisions that are triggered by facts.

## P2 — Verified skill library  *(complexity: M)*

Voyager's reproducible core is not the curriculum, it is that skills enter
the library **only after passing execution**, are stored as callable code
with docstring embeddings, and are retrieved for later tasks.

Aegis Zero already has a tool registry and a memory store; this is the
bridge between them:

```python
@registry.tool(risk=Risk.SAFE)
async def solve_subproblem(...): ...   # promoted from a verified Forge output
```

Admission requires a passing verifier from P1. Without that gate this
becomes a cache of plausible-looking wrong code.

- Wang et al., *Voyager*, TMLR 2024, arXiv:2305.16291

## P3 — Compile prompts instead of hand-tuning them  *(complexity: M)*

The sub-agent prompts are hand-written constants. DSPy treats a pipeline as
a program and optimizes each stage's instructions and few-shot examples
against a stage-level metric.

Realistically this means: define a metric per stage, keep a held-out set,
and optimize offline — not a runtime dependency.

- Khattab et al., *DSPy*, arXiv:2310.03714
- Opsahl-Ong et al., *MIPROv2*, EMNLP 2024, arXiv:2406.11695
- Agrawal et al., *GEPA*, arXiv:2507.19457 (preprint — reports beating RL on
  some tasks; treat the magnitude as unconfirmed)

## P4 — Report reliability, not just success  *(complexity: S)* — **DONE**

τ-bench's contribution is the metric: **pass^k**, the probability that an
agent succeeds *k* times in a row. Agents that look strong at pass@1 collapse
under pass^k — they are unreliable rather than incapable.

The engine can now run a goal *k* times and report the consistency rate,
along with a 95% Wilson interval on pass^k so a small sample does not
masquerade as precision, and the mean tokens / seconds / revisions per run.
Implemented as `Aegis.reliability()` (async, bounded concurrency) and the
`aegis reliability` CLI command.

- Yao et al., *τ-bench*, arXiv:2406.12045

## P5 — Per-model context windows  *(complexity: S)* — **DONE**

`max_tokens` was one global constant. Every model has a different window, so
the prompt budget was wrong for all but one. `ModelSettings` now carries a
per-model `context_windows` registry; the prompt budget for each call is
derived from that model's own window minus a generation reserve, and the
`ContextBuilder` resolves the budget per model at build time. An unknown
model falls back to a conservative `default_context_window`. This closes
audit item #13.

- Reflexion's gains come from an external evaluator, not introspection —

## P6 — Fine-grained memory credit assignment  *(complexity: L)* — **DONE**

Originally every memory retrieved during a successful run received the same
reward, including ones that were never used. This is now closed at two
levels:

1. **Tombstone coherence.** `AgentResult.invalidated_memory_ids` records
   which recalled memories a hard verifier failure disproved, and the
   learner excludes them from the reward (see
   `tests/test_p6_credit_assignment.py`). Rewarding a memory the verifier
   just proved fed a wrong claim would be self-contradictory credit
   assignment.
2. **Cite-level attribution** (the original P6 proposal). Memories are
   rendered into the Forge prompt with stable tags (`[m1]`, `[m2]`, …) and
   credited only on evidence, via two deterministic channels
   (`src/aegis_zero/orchestrator/citations.py`):
   - **Declared:** the reply ends with `MEMORIES USED: m1, m3`; the line is
     parsed leniently, stripped before the answer flows downstream, and
     tags map back to episode ids through the packet. A declared citation
     earns the full run signal.
   - **Grounded:** a memory whose *rendered* text reappears verbatim in the
     reply (6-word n-gram overlap) demonstrably influenced the output even
     when the model forgot to cite it. Undeclared reuse earns half the
     signal.
   - A recalled memory that is neither declared nor grounded earns nothing —
     absence of use is not evidence of harm, so it is not punished either.
     Tombstoned memories are excluded from both channels. Every run with
     recalled memories emits a `memory.credit` event (including the
     zero-credit cases the P6 fine-grained-attribution metric needs).
   - `EngineConfig.citation_protocol=False` restores the legacy coarse
     reward as an ablation switch, so the two policies can be A/B-measured
     rather than asserted (see `tests/test_cite_level_attribution.py`,
     23 tests).

**Honest limits, pinned by tests:** the declared channel trusts the model's
own report (a model that never cites disables the channel, and a lying model
weakens it — the grounding channel is the backstop, not a replacement), and
grounding detects verbatim reuse only, not paraphrase. Reward quality is
still bounded by the verifier that produces the signal, hence P1 first.

Do this after P1, because the reward signal is only as good as the verifier
that produces it.

## P6.5 — Temporal validity and contradiction handling  *(complexity: M)* — **DONE**

The memory store has no notion of *when* a fact was true. A memory such as
"the user lives in X" can become false and still rank highly, and two
contradictory memories about the same entity coexist with no way to decide
which is current. This directly poisons generations and is the highest-value
gap the memory audit surfaced that the earlier fixes did not touch.

**Implemented** (see `tests/test_temporal_validity.py`, 6 tests):

Design (lowest-risk version, no new ML):

- Each episode stores an `(asserted_at, valid_until)` pair.
- On write, run a cheap contradiction check against existing episodes that
  share the same normalized entity key (the same kind of identity match the
  policy engine already does for paths/hosts). On conflict, set the older
  episode's `valid_until` and flag it deprecated rather than deleting it.
- Ranking multiplies by a validity gate: `1.0` while valid, decaying toward
  `0.0` after `valid_until`.
- An explicit invalidation path, triggered by a verifier (P1) detecting a
  wrong claim, sets `valid_until = now` on the responsible memory.

Keep it as tombstoning, not deletion, so the corpus stays reversible for
ablation. This is independent of P6 (which is about *credit*, this about
*validity*) and does not need the verifier first.

---

## Corrections to the research inputs

Two claims from the memory-architecture sub-report were checked against the
code and the running system, and are **not** accurate as applied here:

- *"There is no decay."* False. `MemRLEngine.consolidate()` subtracts
  `decay_per_batch * log1p(retrievals)` from every unused episode each
  consolidation pass, and prunes below `prune_below`. The decay exists; it is
  only absent from the *per-reward* rule, which is a different (and minor)
  point.
- *"Repeated success pushes score to infinity; the update rule has a dead
  zone."* False. The rule is `score += lr * (reward - tanh(score))`, which
  is self-limiting: 500 consecutive `+1` rewards reach `2.64`, and `pytest`
  pins this. There is no divergence and no saturation dead zone in practice.

The sub-report's valid findings — coarse credit assignment (P6, since
closed at cite level), popularity bias (fixed in AUDIT-10), and temporal
validity (P6.5) — are the ones captured above. Its suggestion to *learn*
the ranking weights via
a pointwise model is reasonable but premature until P1/P6 give a trustworthy
label signal.

---

## Deliberately not doing

**Self-modifying agent code** (Darwin Gödel Machine, arXiv:2505.22954; ADAS,
arXiv:2408.08435). Unreproduced independently, expensive, documents its own
reward hacking, and an arbitrary-code-execution hazard in a framework whose
entire premise is policy-governed execution. The contradiction is fatal.

**End-to-end "AI Scientist" paper generation** (arXiv:2408.06292,
arXiv:2504.08066). The famous "accepted at an ICLR workshop" result is 1 of
3 submissions, self-selected by an LLM reviewer that is the same model family
as the generator. Optimizing against your own judge is Goodhart's law with
extra steps.

**Multi-agent debate as a default.** Gains often vanish against a well-tuned
single agent given the same token budget (Cemri et al., 2025, preprint).
Aegis Zero already has parallel subtasks, which capture most of the benefit
without N× cost.

**Tree search (LATS/ToT) in the main loop.** Real gains on search-shaped
problems with a cheap scorer, but it multiplies cost on everything else.
Worth revisiting only once P1 provides a scorer worth searching against.

---

## How to know whether any of this worked

Without measurement this document is a wish list. Minimum bar before
claiming an improvement:

1. A fixed held-out set of goals with checkable answers.
2. Fixed seeds; report mean ± stddev over ≥3 runs.
3. pass^k alongside pass@1 (P4).
4. Tokens and wall-clock per run, since most "improvements" are really
   just spending more compute.
5. An honest baseline: the same model, same budget, no scaffolding. Many
   framework gains disappear against that comparison.
