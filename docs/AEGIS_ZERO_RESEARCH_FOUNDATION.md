# Aegis Zero: Research-Backed Foundation, Gap Analysis, and Build Order

## Scope

This document is a scientific grounding pass over the current `Aegis-Zero` workspace as of 2026-04-16.

It has three goals:

1. Separate evidence-backed agent design from architectural hype.
2. Identify stop-ship issues in the current repo.
3. Define the shortest credible path to a secure, local-first, autonomous agent system.

This is not a marketing document. It is a build document.

## Executive Judgment

The current repo is not a finished autonomous agent. It is a promising architecture sketch plus several partially implemented Python modules and integration notes.

The strongest parts are:

- Explicit orchestration instead of free-form agent loops.
- Separation of reasoning, execution, memory, and review.
- Local-first deployment assumptions.
- A serious security mindset.

The weakest parts are:

- Missing core runtime modules that the code imports.
- Security controls described in prose but not enforced in code.
- Reliance on self-reported confidence and LLM-only auditing.
- No real evaluation harness against modern agent benchmarks.
- No prompt-injection boundary enforcement despite tool and retrieval plans.

Bottom line:

- The high-level direction is defensible.
- The current implementation is not yet safe or scientifically validated enough to call "extremely secure autonomous."
- The next milestone should be a minimal trustworthy agent core, not more conceptual innovations.

## What the Literature Actually Supports

### 1. Explicit tool use and reason-act loops are real

The design choice to keep control flow explicit and let Python decide what happens next is supported.

- ReAct shows that interleaving reasoning and action improves performance and interpretability for grounded tasks: https://arxiv.org/abs/2210.03629
- Toolformer supports explicit external tool use rather than expecting the base model to solve everything internally: https://arxiv.org/abs/2302.04761

Implication for Aegis Zero:

- Keep orchestration outside the model.
- Keep tool schemas structured.
- Do not let the model invent hidden control flow.

### 2. Memory helps, but naive retrieval is not enough

The repo's intuition that passive semantic retrieval is noisy is consistent with the literature.

- Reflexion shows that verbal feedback plus episodic memory can improve future performance without weight updates: https://arxiv.org/abs/2303.11366
- Voyager shows persistent skill libraries and iterative error-driven improvement can compound capabilities over time: https://arxiv.org/abs/2305.16291
- CoALA provides a useful modular framing for memory, tools, and decision-making in language agents: https://arxiv.org/abs/2309.02427
- MemRL directly supports value-aware episodic retrieval and runtime improvement without fine-tuning: https://arxiv.org/abs/2601.03192

Implication for Aegis Zero:

- A memory layer is justified.
- A utility-weighted memory layer is plausible.
- But memory updates need measured rewards, not hand-wavy heuristics alone.

### 3. Multi-agent orchestration can help, but it is not automatically better

The "puppeteer" concept is now supported by recent work, but only when the orchestration policy is disciplined and evaluated.

- Multi-Agent Collaboration via Evolving Orchestration supports a centralized puppeteer that dynamically sequences specialists: https://arxiv.org/abs/2505.19591

Implication for Aegis Zero:

- Scout/Forge/Auditor is a reasonable structure.
- But every added agent increases attack surface, latency, and coordination failure modes.
- Multi-agent should be opt-in for hard tasks, not the default religion.

### 4. Real-world agent benchmarks remain brutal

Modern benchmarks show that long-horizon autonomous agents are still unreliable.

- SWE-bench frames real software engineering as a hard environment where models historically resolve only a limited subset of issues: https://arxiv.org/abs/2310.06770
- WebArena reports that realistic web tasks remain difficult, with a strong GPT-4 web agent far below human performance in the paper's evaluation: https://openreview.net/forum?id=oKn9c6ytLx
- OSWorld shows similarly large gaps between agents and humans in real computer environments: https://arxiv.org/abs/2404.07972

Implication for Aegis Zero:

- "Autonomous" must mean bounded autonomy with measurable fallback, not unrestricted self-direction.
- Claims like "zero effort" or "production-grade autonomy" require benchmark evidence, not architecture diagrams.

### 5. Prompt injection is a first-class security problem

If the agent reads web pages, emails, documents, or untrusted memory and can take actions, prompt injection is not optional background risk. It is core risk.

- BIPIA shows indirect prompt injection is a broad vulnerability class for LLM-integrated systems and that instruction/content separation matters: https://www.microsoft.com/en-us/research/publication/benchmarking-and-defending-against-indirect-prompt-injection-attacks-on-large-language-models/
- InjecAgent shows tool-integrated agents are vulnerable to indirect prompt injection and data exfiltration attacks: https://arxiv.org/abs/2403.02691
- The Instruction Hierarchy argues that models need explicit instruction priority handling to resist hostile lower-trust inputs: https://openai.com/index/the-instruction-hierarchy/

Implication for Aegis Zero:

- Every external artifact must carry trust labels.
- Retrieved content must be treated as data by default, never as instructions.
- Tool calls require policy checks independent of model intent.

### 6. Capable agents increase cyber risk, so sandboxing must be real

- Teams of LLM Agents can Exploit Zero-Day shows multi-agent systems can materially increase offensive cyber capability: https://arxiv.org/abs/2406.01637

Implication for Aegis Zero:

- "Extremely secure" means capability containment, not just private hosting.
- Zero public ports is good, but not sufficient.
- The local agent still needs strict execution policy, secret isolation, and auditability.

## Stop-Ship Issues in the Current Repo

### 1. The codebase is not self-contained

`puppeteer.py` imports `ContextEngine` and `MemoryWriter` from an absolute path that does not exist in this repo.

Reference:

- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:59)

Impact:

- The main orchestration path cannot run from this workspace alone.
- Reproducibility is broken.

### 2. Security is mostly described, not enforced

The code talks about approval gates, typed tools, and zero-trust boundaries, but there is no actual policy engine that:

- classifies tools by risk,
- enforces allow/deny rules,
- sanitizes retrieved content by trust tier,
- blocks secrets from flowing into prompts,
- or proves write/command actions were authorized.

References:

- [agent_harness.py](/home/khalid/Dokumente/Aegis-Zero/agent_harness.py:279)
- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:287)

Impact:

- The system is not yet secure in the sense that current agent-security literature requires.

### 3. Auditor-as-LLM is not a sufficient safety boundary

The current Auditor is another model call over the Forge output.

Reference:

- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:409)

Impact:

- This can improve quality.
- It cannot be your final security control for file writes, shell actions, network access, or exfiltration.

Required correction:

- Use deterministic policy checks for high-risk actions.
- Keep the Auditor as advisory, not authoritative.

### 4. Semantic cache can become a prompt-injection persistence layer

The Scout short-circuits on cached responses, and the system later stores final responses in `semantic_cache`.

References:

- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:262)
- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:629)

Impact:

- Poisoned or low-quality outputs can be replayed.
- There is no trust decay, provenance, or cache invalidation policy.

### 5. MemRL reward signals are plausible, but not yet scientifically reliable

The memory engine currently assumes heuristics such as "user continued conversation" implies positive reward.

Reference:

- [memrl_engine.py](/home/khalid/Dokumente/Aegis-Zero/memrl_engine.py:332)

Impact:

- This may encode false positives.
- It can reinforce long but bad conversations.
- It can distort retrieval without benchmark validation.

Required correction:

- Measure memory utility against explicit task outcomes, regression suites, or user-approved success signals.

### 6. Hardcoded deployment assumptions break portability

Examples:

- fixed localhost Qdrant endpoint,
- fixed absolute context path,
- fixed vector size assumptions.

References:

- [agent_harness.py](/home/khalid/Dokumente/Aegis-Zero/agent_harness.py:115)
- [memrl_engine.py](/home/khalid/Dokumente/Aegis-Zero/memrl_engine.py:207)
- [puppeteer.py](/home/khalid/Dokumente/Aegis-Zero/puppeteer.py:59)

Impact:

- The system is not reproducible enough for serious testing or deployment.

### 7. There is no benchmark harness

The repo currently has architecture docs and modules, but no evaluation suite that tests:

- tool correctness,
- prompt-injection resistance,
- memory retrieval quality,
- regression on past tasks,
- or end-to-end success rates.

Impact:

- You cannot tell whether Aegis Zero is improving or degrading.

## What To Build Next

### Phase 1: Minimal Trusted Core

Goal: one bounded agent loop that is actually safe enough to test.

Build:

- a local policy engine for tool permissions,
- a trust-labeled context builder,
- a deterministic action gate for shell/file/network classes,
- a sealed execution sandbox for agent actions,
- structured traces for every step.

Do not build yet:

- parallel subagents,
- nightly self-improvement,
- autonomous internet research,
- automatic memory reward shaping.

Reason:

- Without policy and evaluation, those features amplify risk faster than capability.

### Phase 2: Secure Retrieval and Memory

Goal: retrieval that improves accuracy without becoming an injection channel.

Build:

- provenance fields for each memory/document,
- trust labels such as `system`, `user`, `retrieved_external`, `model_generated`,
- prompt templates that treat untrusted retrieval as quoted data,
- cache invalidation and TTL,
- explicit success/failure memory events.

Then add:

- utility-aware retrieval like MemRL,
- but only after outcome labeling exists.

### Phase 3: Evaluation Before More Autonomy

Goal: prove the system improves.

Build three suites:

1. Safety suite
- prompt injection attempts,
- secret exfiltration attempts,
- unsafe command-generation attempts.

2. Capability suite
- local coding tasks,
- retrieval tasks,
- multi-step file manipulation tasks.

3. Regression suite
- replay past successful tasks and verify no degradation.

### Phase 4: Conditional Multi-Agent Expansion

Goal: add Scout/Forge/Auditor only where it earns its cost.

Rules:

- use a single-agent path by default,
- add Scout for retrieval-heavy tasks,
- add Auditor for high-value outputs,
- add parallel workers only after you can measure win rates.

## The Correct Security Model for Aegis Zero

If the design target is "extremely secure", the real architecture should be:

1. Model
- untrusted planner, not root authority.

2. Policy engine
- trusted component that approves or rejects actions.

3. Retrieval boundary
- untrusted content is data only.

4. Execution sandbox
- least privilege, no implicit ambient authority.

5. Observability
- every action and prompt lineage recorded.

6. Human override
- required for irreversible or high-risk actions.

Anything weaker is still useful, but it is not "zero compromise."

## Recommended Immediate Repo Direction

The next concrete repository milestone should be:

`Aegis Zero v0: Trusted Local Agent Kernel`

That milestone should contain only:

- a real `ContextEngine`,
- a real policy-enforced tool registry,
- a real orchestration loop,
- a real test harness,
- and a minimal secure memory layer.

It should explicitly exclude:

- unsupported marketing claims,
- benchmark-free self-improvement claims,
- and autonomous action features without containment.

## Sources

Primary sources used here:

- ReAct: https://arxiv.org/abs/2210.03629
- Toolformer: https://arxiv.org/abs/2302.04761
- Reflexion: https://arxiv.org/abs/2303.11366
- Voyager: https://arxiv.org/abs/2305.16291
- CoALA: https://arxiv.org/abs/2309.02427
- SWE-bench: https://arxiv.org/abs/2310.06770
- BIPIA / indirect prompt injection: https://www.microsoft.com/en-us/research/publication/benchmarking-and-defending-against-indirect-prompt-injection-attacks-on-large-language-models/
- InjecAgent: https://arxiv.org/abs/2403.02691
- Instruction Hierarchy: https://openai.com/index/the-instruction-hierarchy/
- OSWorld: https://arxiv.org/abs/2404.07972
- Multi-Agent Collaboration via Evolving Orchestration: https://arxiv.org/abs/2505.19591
- MemRL: https://arxiv.org/abs/2601.03192
- Teams of LLM Agents can Exploit Zero-Day: https://arxiv.org/abs/2406.01637

## Recommended Next Step

Implement the trusted local agent kernel first.

If you want, the next turn should be one of these:

1. I turn this research foundation into a concrete repo roadmap with file-by-file implementation tasks.
2. I start building the trusted kernel directly in this workspace.
3. I perform a code-review style pass and patch the highest-risk architectural problems first.
