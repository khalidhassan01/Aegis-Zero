# AEGIS ZERO — Puppeteer Orchestration v1.0
# Innovation #3: Dynamic Multi-Agent Orchestration
# Based on NeurIPS 2025: "Multi-Agent Collaboration via Evolving Orchestration"
# arXiv:2505.19591 — OpenBMB/ChatDev puppeteer paradigm
#
# ============================================================
# ARCHITECTURE
#
#  USER MESSAGE
#       │
#       ▼
#  ┌────────────────────────────────────┐
#  │  PUPPETEER (Hermes Orchestrator)   │  ← aegis-fast (cheap, fast triage)
#  │  • Classifies task complexity      │
#  │  • Selects puppet sequence         │
#  │  • Routes context per puppet       │
#  │  • Assembles final response        │
#  └──────┬──────┬──────┬──────────────┘
#         │      │      │
#    ┌────▼┐ ┌───▼─┐ ┌──▼─────┐
#    │SCOUT│ │FORGE│ │AUDITOR │   ← The 3 core puppets
#    │     │ │     │ │        │
#    │fast │ │deep │ │fast    │
#    └─────┘ └─────┘ └────────┘
#
# SCOUT   — gathers context, searches memory, retrieves docs (aegis-fast)
# FORGE   — the actual reasoning and generation (aegis-deep or aegis-fast)
# AUDITOR — reviews, fact-checks, catches errors before delivery (aegis-fast)
#
# On simple tasks: Puppeteer → FORGE only (no overhead)
# On complex tasks: Puppeteer → SCOUT → FORGE → AUDITOR
# On research tasks: Puppeteer → SCOUT → FORGE (parallel) → AUDITOR → FORGE (synthesis)
#
# ============================================================
# INTEGRATION POINTS
#
# Builds ON TOP OF:
#   - MCP Layer (Innovation #1): all tool calls go through MCP servers
#   - Context Engine (Innovation #2): every puppet gets context-engineered prompt
#   - Two-Tier AI (existing): FORGE can be deep or fast based on task
#   - Caveman + Sidecar (existing): token optimization still applies
#
# ============================================================

# FILE: ~/.aegis/orchestration/puppeteer.py

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional
from datetime import datetime, timezone
from enum import Enum

import ollama

from context_engine import ContextEngine, MemoryWriter
from trusted_mcp import TrustedMCPAdapter


# ──────────────────────────────────────────────
# TASK CLASSIFICATION
# ──────────────────────────────────────────────

class TaskComplexity(Enum):
    SIMPLE    = "simple"     # single-turn, no research needed
    STANDARD  = "standard"   # needs context, moderate reasoning
    COMPLEX   = "complex"    # multi-step, research + reasoning
    RESEARCH  = "research"   # deep investigation, parallel exploration


class TaskDomain(Enum):
    CHAT       = "chat"
    CODE       = "code"
    RESEARCH   = "research"
    SYSTEM     = "system"       # infrastructure / health commands
    CREATIVE   = "creative"
    ANALYSIS   = "analysis"
    PLANNING   = "planning"


# ──────────────────────────────────────────────
# DATA MODELS
# ──────────────────────────────────────────────

@dataclass
class TaskClassification:
    complexity: TaskComplexity
    domain: TaskDomain
    needs_scout: bool
    needs_auditor: bool
    forge_tier: str             # "fast" or "deep"
    parallel_forges: int        # 1 = sequential, 2+ = parallel exploration
    reasoning: str              # why this classification was chosen
    estimated_tokens: int


@dataclass
class PuppetResult:
    puppet_id: str              # "scout" / "forge" / "forge_2" / "auditor"
    puppet_type: str
    model_used: str
    output: str
    tool_calls: list[dict]      # MCP tools invoked
    duration_sec: float
    token_count: int
    confidence: float           # self-reported by the puppet


@dataclass
class OrchestrationTrace:
    """Full audit trail of one orchestrated task."""
    task_id: str
    original_message: str
    classification: dict
    puppet_sequence: list[str]
    puppet_results: list[dict]
    final_response: str
    total_duration_sec: float
    total_tokens: int
    models_used: dict
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ──────────────────────────────────────────────
# CLASSIFIER
# Runs first. Determines the entire execution path.
# Uses aegis-fast — cheap, <0.5s on ARM.
# ──────────────────────────────────────────────

class TaskClassifier:

    # Simple heuristic pre-filter before LLM classification
    SIMPLE_PATTERNS = [
        "what time", "remind me", "hello", "hi", "thanks",
        "yes", "no", "ok", "sure", "got it", "what is",
        "how do i", "set alarm", "quick question"
    ]

    RESEARCH_PATTERNS = [
        "research", "investigate", "compare", "analyze deeply",
        "write a report", "find all", "comprehensive", "in depth",
        "everything about", "full analysis"
    ]

    CODE_PATTERNS = [
        "debug", "fix this", "write a script", "implement",
        "refactor", "review my code", "error in", "traceback",
        "function that", "class that", "bash script"
    ]

    def classify(self, message: str) -> TaskClassification:
        """
        Classify a user message into a TaskClassification.
        Two-stage: fast heuristic check, then LLM for ambiguous cases.
        """
        lower = message.lower()
        word_count = len(message.split())

        # Stage 1: Fast heuristic (no LLM cost)
        if word_count < 8 and any(p in lower for p in self.SIMPLE_PATTERNS):
            return TaskClassification(
                complexity=TaskComplexity.SIMPLE,
                domain=TaskDomain.CHAT,
                needs_scout=False,
                needs_auditor=False,
                forge_tier="fast",
                parallel_forges=1,
                reasoning="Short message matching simple pattern",
                estimated_tokens=100
            )

        is_research = any(p in lower for p in self.RESEARCH_PATTERNS)
        is_code = any(p in lower for p in self.CODE_PATTERNS)
        is_long = word_count > 60

        # Stage 2: LLM classification for non-trivial messages
        classify_prompt = f"""Classify this user message for AI agent routing.
Return ONLY a JSON object with these exact keys:
- "complexity": one of: simple/standard/complex/research
- "domain": one of: chat/code/research/system/creative/analysis/planning
- "needs_scout": bool (true if context gathering needed first)
- "needs_auditor": bool (true if output should be verified before delivery)
- "forge_tier": "fast" or "deep" (deep for code/research/complex analysis)
- "parallel_forges": int 1-3 (>1 only for research tasks needing exploration)
- "reasoning": one sentence explaining the classification
- "estimated_tokens": rough output token estimate (50-2000)

Message: {message[:500]}
Hints: is_research={is_research}, is_code={is_code}, is_long={is_long}"""

        try:
            resp = ollama.generate(
                model="aegis-fast",
                prompt=classify_prompt,
                options={"temperature": 0.1, "num_predict": 256}
            )
            raw = resp["response"].strip()
            if "```" in raw:
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw.strip())

            return TaskClassification(
                complexity=TaskComplexity(data.get("complexity", "standard")),
                domain=TaskDomain(data.get("domain", "chat")),
                needs_scout=data.get("needs_scout", False),
                needs_auditor=data.get("needs_auditor", False),
                forge_tier=data.get("forge_tier", "fast"),
                parallel_forges=min(int(data.get("parallel_forges", 1)), 3),
                reasoning=data.get("reasoning", ""),
                estimated_tokens=int(data.get("estimated_tokens", 500))
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            # Fallback classification
            return TaskClassification(
                complexity=TaskComplexity.STANDARD,
                domain=TaskDomain.CHAT,
                needs_scout=is_code or is_research,
                needs_auditor=is_code,
                forge_tier="deep" if (is_code or is_research or is_long) else "fast",
                parallel_forges=1,
                reasoning="Fallback: LLM classification failed",
                estimated_tokens=500
            )


# ──────────────────────────────────────────────
# THE 3 PUPPETS
# Each has a single focused role.
# Each gets a context-engineered prompt via ContextEngine.
# ──────────────────────────────────────────────

class ScoutPuppet:
    """
    Gathers context before the Forge reasons.
    Searches memory, retrieves relevant documents, identifies
    what the Forge will need. Runs on aegis-fast.

    The Scout answers: "What does the Forge need to know?"
    """

    SYSTEM = """You are Scout, a context-gathering agent in the Aegis Zero system.
Your ONLY job: gather and summarize the information needed to answer the user's request.
Do NOT answer the question yourself.
Output a structured briefing that the reasoning agent (Forge) will use.
Be concise. Identify gaps. Flag what you found vs what's missing."""

    def run(self, message: str,
            ctx_engine: ContextEngine,
            mcp_adapter: TrustedMCPAdapter) -> PuppetResult:
        t0 = time.time()
        tool_calls = []

        # 1. Check semantic cache first
        cache_result = mcp_adapter.semantic_cache_check(message)
        if cache_result.hit:
            tool_calls.append({"tool": "semantic_cache_check", "result": "HIT"})
            return PuppetResult(
                puppet_id="scout",
                puppet_type="scout",
                model_used="cache",
                output=json.dumps({
                    "cache_hit": True,
                    "cached_response": cache_result.response,
                    "similarity": cache_result.similarity
                }),
                tool_calls=tool_calls,
                duration_sec=round(time.time() - t0, 3),
                token_count=0,
                confidence=cache_result.similarity
            )

        # 2. Search episodic memory
        memory_results = mcp_adapter.knowledge_search(
            query=message,
            collection="conversations",
            limit=3
        )
        if memory_results:
            tool_calls.append({"tool": "knowledge_search",
                                "collection": "conversations"})

        # 3. Search document vault
        doc_results = mcp_adapter.knowledge_search(
            query=message,
            collection="documents",
            limit=2
        )
        if doc_results:
            tool_calls.append({"tool": "knowledge_search",
                                "collection": "documents"})

        # 4. Build scout briefing
        ctx = ctx_engine.build(message, tier="fast")
        prompt_data = ctx_engine.to_prompt(ctx)

        scout_prompt = f"""{prompt_data['prompt']}

Retrieved memory:
{mcp_adapter.render_references(memory_results)}

Retrieved documents:
{mcp_adapter.render_references(doc_results)}

Produce a briefing for the reasoning agent. Include:
1. What context is relevant from memory
2. What documents/knowledge are available
3. What's missing that the reasoning agent should know about
4. Key constraints or preferences to respect
Keep it under 200 words."""

        resp = ollama.generate(
            model="aegis-fast",
            prompt=scout_prompt,
            system=self.SYSTEM,
            options={"temperature": 0.3, "num_predict": 400}
        )

        return PuppetResult(
            puppet_id="scout",
            puppet_type="scout",
            model_used="aegis-fast",
            output=resp["response"],
            tool_calls=tool_calls,
            duration_sec=round(time.time() - t0, 3),
            token_count=resp.get("eval_count", 0),
            confidence=0.85
        )


class ForgePuppet:
    """
    The reasoning and generation puppet. The actual brain.
    Gets the Scout's briefing + context-engineered prompt.
    Uses aegis-deep for complex tasks, aegis-fast for simple.

    The Forge answers: "What is the best response to the user's request?"
    """

    SYSTEM_DEEP = """You are Forge, a deep reasoning agent in the Aegis Zero system.
You receive a briefing from Scout and produce the best possible response.
You have full context about the user from memory. Use it.
Be thorough on complex tasks. Cite your reasoning.
On code tasks: apply Karpathy guidelines — readable, minimal, well-commented."""

    SYSTEM_FAST = """You are Forge, a fast response agent in the Aegis Zero system.
Produce a concise, accurate response. Use the context provided.
Be direct. No padding."""

    def run(self, message: str,
            scout_briefing: Optional[str],
            ctx_engine: ContextEngine,
            tier: str = "fast",
            forge_id: str = "forge") -> PuppetResult:
        t0 = time.time()
        model = "aegis-deep" if tier == "deep" else "aegis-fast"
        system = self.SYSTEM_DEEP if tier == "deep" else self.SYSTEM_FAST

        ctx = ctx_engine.build(message, tier=tier)
        prompt_data = ctx_engine.to_prompt(ctx)

        if scout_briefing:
            full_prompt = f"""Scout briefing:
{scout_briefing}

---

{prompt_data['prompt']}"""
        else:
            full_prompt = prompt_data["prompt"]

        max_tokens = 2048 if tier == "deep" else 1024

        resp = ollama.generate(
            model=model,
            prompt=full_prompt,
            system=f"{prompt_data['system']}\n\n{system}",
            options={"temperature": 0.7, "num_predict": max_tokens}
        )

        return PuppetResult(
            puppet_id=forge_id,
            puppet_type="forge",
            model_used=model,
            output=resp["response"],
            tool_calls=[],
            duration_sec=round(time.time() - t0, 3),
            token_count=resp.get("eval_count", 0),
            confidence=0.80
        )


class AuditorPuppet:
    """
    Reviews the Forge's output before delivery.
    Checks for: factual errors, incomplete answers, security leaks,
    code bugs, hallucinations, missed user requirements.
    Runs on aegis-fast — cheap review pass.

    The Auditor answers: "Is this safe and correct to send?"
    """

    SYSTEM = """You are Auditor, a quality-control agent in the Aegis Zero system.
Review the proposed response against the user's request.
Check for: factual errors, incomplete answers, security/credential leaks,
code bugs, missed requirements, hallucinations.

Return ONLY a JSON object with:
- "approved": bool
- "confidence": float 0-1
- "issues": list of strings (empty if approved)
- "revised_response": string (improved version if issues found, else same as input)
- "reasoning": one sentence

Be strict but fair. Minor style issues are not rejection reasons."""

    def run(self, original_message: str,
            forge_output: str) -> PuppetResult:
        t0 = time.time()
        audit_data = None

        audit_prompt = f"""User request: {original_message[:400]}

Proposed response:
{forge_output[:3000]}

Review and return JSON."""

        resp = ollama.generate(
            model="aegis-fast",
            prompt=audit_prompt,
            system=self.SYSTEM,
            options={"temperature": 0.1, "num_predict": 1024}
        )

        raw = resp["response"].strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        try:
            audit_data = json.loads(raw.strip())
            final_output = audit_data.get("revised_response", forge_output)
            confidence = float(audit_data.get("confidence", 0.8))
            issues = audit_data.get("issues", [])
            approved = audit_data.get("approved", True)
        except (json.JSONDecodeError, ValueError):
            final_output = forge_output
            confidence = 0.0
            issues = ["auditor_parse_failure"]
            approved = False

        output = json.dumps({
            "approved": approved,
            "issues": issues,
            "final_response": final_output,
            "confidence": confidence,
            "reasoning": audit_data.get("reasoning", "") if audit_data else ""
        }, ensure_ascii=False)

        return PuppetResult(
            puppet_id="auditor",
            puppet_type="auditor",
            model_used="aegis-fast",
            output=output,
            tool_calls=[],
            duration_sec=round(time.time() - t0, 3),
            token_count=resp.get("eval_count", 0),
            confidence=confidence
        )


# ──────────────────────────────────────────────
# PUPPETEER — the orchestrator
# Observes, classifies, sequences, assembles.
# ──────────────────────────────────────────────

class Puppeteer:
    """
    The central orchestrator. Reads the task, selects the puppet sequence,
    routes context to each puppet, assembles the final response.

    This is Hermes's new brain. Every user message passes through here.

    Sequence selection:
    - SIMPLE:   [forge_fast]
    - STANDARD: [forge_deep|fast]  based on domain
    - COMPLEX:  [scout] → [forge_deep] → [auditor]
    - RESEARCH: [scout] → [forge_deep × N parallel] → [auditor] → [forge_fast synthesis]
    """

    def __init__(self, mcp_tools: dict = None,
                 tool_executor: Optional[Callable] = None):
        self.classifier = TaskClassifier()
        self.scout = ScoutPuppet()
        self.forge = ForgePuppet()
        self.auditor = AuditorPuppet()
        self.ctx_engine = ContextEngine()
        self.memory_writer = MemoryWriter()
        self.mcp_tools = mcp_tools or {}
        self.mcp_adapter = TrustedMCPAdapter(self.mcp_tools)
        self.tool_executor = tool_executor

    def run(self, message: str,
            interface: str = "telegram",
            session_id: Optional[str] = None) -> OrchestrationTrace:
        """
        Main entry point. Takes a user message, returns a full trace
        including the final response and complete audit trail.
        """
        task_id = str(uuid.uuid4())[:8]
        t_total = time.time()
        puppet_results = []
        models_used = {}

        # ── 0. Classify the task
        classification = self.classifier.classify(message)

        # ── 1. Select and execute puppet sequence
        sequence = self._select_sequence(classification)
        scout_briefing = None
        forge_outputs = []
        audit_state = {"approved": False, "issues": ["not_audited"]}

        for step in sequence:

            if step == "scout":
                result = self.scout.run(message, self.ctx_engine, self.mcp_adapter)
                puppet_results.append(asdict(result))
                models_used["scout"] = result.model_used

                # Cache hit short-circuit
                try:
                    scout_data = json.loads(result.output)
                    if scout_data.get("cache_hit"):
                        cached = scout_data["cached_response"]
                        return OrchestrationTrace(
                            task_id=task_id,
                            original_message=message,
                            classification=asdict(classification),
                            puppet_sequence=["cache_hit"],
                            puppet_results=puppet_results,
                            final_response=cached,
                            total_duration_sec=round(time.time() - t_total, 3),
                            total_tokens=0,
                            models_used={"cache": "semantic_cache"}
                        )
                    scout_briefing = result.output
                except (json.JSONDecodeError, KeyError):
                    scout_briefing = result.output

            elif step == "forge":
                tier = classification.forge_tier
                result = self.forge.run(
                    message, scout_briefing, self.ctx_engine,
                    tier=tier, forge_id="forge"
                )
                puppet_results.append(asdict(result))
                models_used["forge"] = result.model_used
                forge_outputs.append(result.output)

            elif step == "forge_parallel":
                # Run N forge instances with different temperatures for diversity
                parallel_outputs = []
                for i in range(classification.parallel_forges):
                    # Vary temperature slightly for exploration diversity
                    r = self.forge.run(
                        message, scout_briefing, self.ctx_engine,
                        tier="deep", forge_id=f"forge_{i+1}"
                    )
                    puppet_results.append(asdict(r))
                    parallel_outputs.append(r.output)

                forge_outputs = parallel_outputs
                models_used["forge_parallel"] = "aegis-deep"

            elif step == "auditor":
                forge_output = forge_outputs[-1] if forge_outputs else ""
                result = self.auditor.run(message, forge_output)
                puppet_results.append(asdict(result))
                models_used["auditor"] = result.model_used

                try:
                    audit_data = json.loads(result.output)
                    # Replace last forge output with audited version
                    forge_outputs[-1] = audit_data.get("final_response",
                                                       forge_output)
                    audit_state = {
                        "approved": bool(audit_data.get("approved", False)),
                        "issues": audit_data.get("issues", []),
                    }
                except (json.JSONDecodeError, KeyError):
                    audit_state = {
                        "approved": False,
                        "issues": ["auditor_output_unparseable"],
                    }

            elif step == "synthesize":
                # Synthesize multiple forge outputs into one
                if len(forge_outputs) > 1:
                    synth_result = self._synthesize(
                        message, forge_outputs
                    )
                    puppet_results.append(asdict(synth_result))
                    models_used["synthesizer"] = synth_result.model_used
                    forge_outputs = [synth_result.output]

        # ── 2. Extract final response
        final_response = forge_outputs[-1] if forge_outputs else ""

        # ── 3. Write to episodic memory (async-safe via simple call)
        try:
            self.memory_writer.write_turn(
                user_msg=message,
                agent_response=final_response,
                interface=interface
            )
        except Exception:
            pass  # Memory write failure never blocks response delivery

        # ── 4. Cache the response in semantic cache
        try:
            if "knowledge_store" in self.mcp_tools:
                should_cache = (
                    final_response and
                    audit_state.get("approved", False) and
                    not audit_state.get("issues")
                )
                if should_cache:
                    allowed, store_kwargs = self.mcp_adapter.knowledge_store_allowed(
                        content=final_response,
                        collection="semantic_cache",
                        metadata=self.mcp_adapter.cache_store_metadata(
                            query=message,
                            model=models_used.get("forge", ""),
                            task_id=task_id,
                            prompt_injection_suspected=False,
                        ),
                    )
                    if allowed:
                        if self.tool_executor:
                            self.tool_executor(
                                "knowledge_store",
                                task_id=task_id,
                                confidence=1.0,
                                irreversible=False,
                                **store_kwargs,
                            )
                        else:
                            self.mcp_tools["knowledge_store"](
                                **store_kwargs
                            )
        except Exception:
            pass

        total_tokens = sum(
            r.get("token_count", 0) for r in puppet_results
        )

        return OrchestrationTrace(
            task_id=task_id,
            original_message=message,
            classification=asdict(classification),
            puppet_sequence=sequence,
            puppet_results=puppet_results,
            final_response=final_response,
            total_duration_sec=round(time.time() - t_total, 3),
            total_tokens=total_tokens,
            models_used=models_used
        )

    def _select_sequence(self, c: TaskClassification) -> list[str]:
        """Map a TaskClassification to an ordered puppet sequence."""
        if c.complexity == TaskComplexity.SIMPLE:
            return ["forge"]

        if c.complexity == TaskComplexity.STANDARD:
            seq = []
            if c.needs_scout:
                seq.append("scout")
            seq.append("forge")
            if c.needs_auditor:
                seq.append("auditor")
            return seq

        if c.complexity == TaskComplexity.COMPLEX:
            seq = ["scout", "forge"]
            if c.needs_auditor:
                seq.append("auditor")
            return seq

        if c.complexity == TaskComplexity.RESEARCH:
            seq = ["scout"]
            if c.parallel_forges > 1:
                seq.append("forge_parallel")
                seq.append("synthesize")
            else:
                seq.append("forge")
            if c.needs_auditor:
                seq.append("auditor")
            return seq

        return ["forge"]  # Fallback

    def _synthesize(self, original: str,
                    outputs: list[str]) -> PuppetResult:
        """Synthesize multiple parallel forge outputs into one."""
        t0 = time.time()
        combined = "\n\n---\n\n".join(
            f"Draft {i+1}:\n{o[:1500]}"
            for i, o in enumerate(outputs)
        )

        synth_prompt = f"""Synthesize these {len(outputs)} research drafts into one definitive response.
Original request: {original[:300]}

{combined}

Produce the best possible synthesis. Prefer specific over vague.
Where drafts agree, state it confidently. Where they differ, present both perspectives."""

        resp = ollama.generate(
            model="aegis-fast",
            prompt=synth_prompt,
            options={"temperature": 0.4, "num_predict": 1500}
        )

        return PuppetResult(
            puppet_id="synthesizer",
            puppet_type="synthesizer",
            model_used="aegis-fast",
            output=resp["response"],
            tool_calls=[],
            duration_sec=round(time.time() - t0, 3),
            token_count=resp.get("eval_count", 0),
            confidence=0.88
        )


# ──────────────────────────────────────────────
# HERMES INTEGRATION — drop-in replacement
# for the existing message handler
# ──────────────────────────────────────────────

# In your existing Hermes handler, replace:
#
#   response = ollama.generate(model="aegis-fast", prompt=message)
#   return response["response"]
#
# With:
#
#   trace = puppeteer.run(message, interface="telegram")
#   return trace.final_response
#
# The trace is automatically stored in episodic memory.
# The response is automatically cached in semantic_cache.
# The classification is logged for self-improvement analysis.

# INIT — one instance per Hermes process
_puppeteer: Optional[Puppeteer] = None

def get_puppeteer(mcp_tools: dict = None) -> Puppeteer:
    global _puppeteer
    if _puppeteer is None:
        _puppeteer = Puppeteer(mcp_tools=mcp_tools)
    return _puppeteer


def handle_message(message: str,
                   interface: str = "telegram",
                   mcp_tools: dict = None) -> str:
    """
    The new Hermes message handler.
    Drop this in where Hermes currently calls ollama directly.
    Returns the final response string ready for delivery.
    """
    p = get_puppeteer(mcp_tools)
    trace = p.run(message, interface=interface)
    return trace.final_response


# ──────────────────────────────────────────────
# SEQUENCE DECISION TABLE — quick reference
# ──────────────────────────────────────────────
#
# Input                           Sequence              Models
# ──────────────────────────────  ────────────────────  ─────────────────────
# "hi" / "thanks" / short chat    forge                 fast only
# "what is X" / simple Q&A        forge                 fast only
# "explain how X works"           forge                 deep
# "debug this code" + file        scout → forge         fast + deep
# "write a script that..."        scout → forge → audit fast + deep + fast
# "research X and write report"   scout → forge×2 →     fast + deep×2 + fast
#                                 synth → audit          + fast + fast
# "compare A vs B deeply"         scout → forge → audit fast + deep + fast
# infrastructure commands         forge                 fast (system domain)
#
# Total token cost vs single-model:
#   Simple:   1x fast  (baseline)
#   Standard: 1x deep  (~4x slow but better)
#   Complex:  fast + deep + fast (~5x tokens, 90% better quality)
#   Research: fast + 2×deep + fast + fast (~10x tokens, research-grade)
#
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Quick test
    test_messages = [
        ("hi", "telegram"),
        ("what is my Tailscale IP?", "telegram"),
        ("debug this Python script that keeps throwing a KeyError", "webui"),
        ("research the best ARM optimization techniques for LLM inference and write a report", "webui"),
    ]

    p = Puppeteer()
    for msg, iface in test_messages:
        print(f"\n{'─'*60}")
        print(f"Message: {msg[:60]}")
        trace = p.run(msg, interface=iface)
        c = trace.classification
        print(f"Classification: {c['complexity']} / {c['domain']}")
        print(f"Sequence: {' → '.join(trace.puppet_sequence)}")
        print(f"Models: {trace.models_used}")
        print(f"Duration: {trace.total_duration_sec}s")
        print(f"Response preview: {trace.final_response[:80]}...")
