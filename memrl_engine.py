# AEGIS ZERO — MemRL: Self-Evolution Engine v1.0
# Innovation #8: Runtime Reinforcement Learning on Episodic Memory
# Based on: arXiv:2601.03192 (Jan 2026) — MemTensor/MemRL
# "MemRL: Self-Evolving Agents via Runtime RL on Episodic Memory"
# Shanghai Jiao Tong University / Linux Foundation AAIF
#
# ============================================================
# THE CORE INSIGHT
#
# The problem with Innovation #2 (Context Engineering):
#   Episodic retrieval uses PASSIVE SEMANTIC MATCHING.
#   Two episodes that LOOK similar may have DIFFERENT utility.
#   Example: "debug Python KeyError" → episode A (resolved in 1 turn)
#                                    → episode B (took 5 turns, wrong approach)
#   Semantic similarity: A ≈ B ≈ 0.91
#   Actual utility:      A = 0.95,  B = 0.12
#   Passive RAG retrieves BOTH. MemRL retrieves ONLY A.
#
# The MemRL solution: Intent-Experience-Utility triplets.
#   z_i = intent embedding (what was asked)
#   e_i = experience (what the agent did — the response trajectory)
#   Q_i = learned utility (how well it actually worked — updated by feedback)
#
# Two-Phase Retrieval:
#   Phase A: Semantic recall   → top-k1 candidates by cosine similarity
#   Phase B: Value-aware select → top-k2 by Q-value from Phase A pool
#
# Q-value update (EMA — Exponential Moving Average):
#   Q_new = α * reward + (1 - α) * Q_old
#   reward = implicit signal from user behaviour + Auditor confidence
#   α = 0.3 (learning rate — slower = more stable)
#
# ============================================================
# AEGIS ZERO MAPPING
#
# z_i  → nomic-embed-text embedding of the user's intent
#         Stored as Qdrant vector in 'conversations' collection
#
# e_i  → EpisodicMemory.summary (compressed interaction)
#         Already written by MemoryWriter.write_turn() after every turn
#
# Q_i  → New field added to EpisodicMemory payload: "q_value"
#         Starts at 0.5 (neutral). Updated by feedback signals.
#
# Reward signals (no human labelling required):
#   +  Auditor approved (confidence > 0.80)         → reward = 0.85
#   +  User sent follow-up (conversation continued)  → reward = 0.75
#   +  Task marked "resolved" in episode             → reward = 0.70
#   −  Auditor revised significantly                 → reward = 0.30
#   −  User sent correction ("that's wrong", "no")  → reward = 0.15
#   −  Task marked "abandoned"                       → reward = 0.10
#
# ============================================================
# INTEGRATION POINTS
#
# Upgrades Innovation #2 (Context Engine):
#   ContextEngine.get_recent_episodes() → replaced by MemRL retrieval
#   Phase A: semantic search (existing)
#   Phase B: Q-value re-ranking (new)
#
# Uses Innovation #1 (MCP):
#   knowledge_search() Phase A, knowledge_store() Q-value writes
#
# Uses Innovation #6 (12-Factor):
#   ObservabilityStore feedback signals drive Q-value updates
#   CheckpointStore task outcomes provide delayed reward
#
# Runs in:
#   Nightly cron (02:00) — batch Q-value updates from accumulated feedback
#   After every Auditor run — immediate Q-value signal
#   ContextEngine.build() — Two-Phase retrieval (replaces passive RAG)
#
# ============================================================

# FILE: ~/.aegis/memrl/memrl_engine.py

import json
import time
import uuid
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import ollama
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from aegis_config import (
    get_embed_model,
    get_qdrant_host,
    get_qdrant_port,
    get_telegram_bot_token,
    get_telegram_chat_id,
)


# ──────────────────────────────────────────────
# CONSTANTS — tuned for Aegis Zero's usage pattern
# ──────────────────────────────────────────────

# Two-Phase Retrieval parameters
K1 = 20          # Phase A: retrieve top-K1 by semantic similarity
K2 = 4           # Phase B: select top-K2 by Q-value from Phase A pool
SIMILARITY_THRESHOLD = 0.65   # Minimum cosine similarity for Phase A

# Q-value parameters
Q_INIT    = 0.50   # Starting Q-value — neutral, no prior belief
Q_ALPHA   = 0.30   # EMA learning rate (0.3 = measured update, not reactive)
Q_MIN     = 0.01   # Floor — never fully discard a memory
Q_MAX     = 0.99   # Ceiling

# Reward signals (implicit — no human labelling)
REWARDS = {
    "auditor_approved_high":    0.90,   # Auditor confidence > 0.85
    "auditor_approved":         0.75,   # Auditor approved (any confidence)
    "conversation_continued":   0.70,   # User sent follow-up message
    "task_resolved":            0.65,   # Episode outcome = "resolved"
    "task_ongoing":             0.50,   # Neutral — no signal either way
    "auditor_revised":          0.30,   # Auditor rewrote the response
    "user_correction":          0.15,   # User sent correction keyword
    "task_abandoned":           0.10,   # Episode outcome = "abandoned"
    "no_signal":                0.50,   # Default — no feedback received
}

# Correction detection keywords
CORRECTION_KEYWORDS = [
    "that's wrong", "incorrect", "not right", "you're wrong",
    "that's not", "that doesn't", "no that", "wrong approach",
    "bad answer", "try again", "fix that"
]


# ──────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────

@dataclass
class MemoryTriplet:
    """
    The core MemRL data structure.
    (z_i, e_i, Q_i) — intent embedding, experience, utility.
    Stored in Qdrant conversations collection with q_value payload field.
    """
    episode_id: str          # Links to existing EpisodicMemory in Qdrant
    intent_text: str         # Original user query (for embedding)
    experience: str          # Compressed episode summary (e_i)
    q_value: float           # Learned utility Q_i ∈ [0.01, 0.99]
    reward_history: list[float]  # Reward signals received so far
    retrieval_count: int     # How many times this was retrieved (Phase A)
    selection_count: int     # How many times this made it through Phase B
    last_rewarded: Optional[str]
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class RetrievalResult:
    """Result from Two-Phase Retrieval."""
    episode_id: str
    experience: str          # e_i — the actual episode summary
    intent_text: str         # z_i — what was originally asked
    q_value: float           # Current Q_i
    similarity: float        # Phase A cosine similarity
    phase_a_rank: int        # Rank in Phase A (1 = most similar)
    phase_b_rank: int        # Rank in Phase B (1 = highest Q-value)
    combined_score: float    # Weighted combination for final ordering


@dataclass
class FeedbackSignal:
    """A reward signal to update a memory's Q-value."""
    episode_id: str
    reward_type: str         # Key from REWARDS dict
    reward_value: float
    source: str              # "auditor" / "user_continuation" / "outcome" / "correction"
    task_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ──────────────────────────────────────────────
# MEMRL ENGINE
# The heart of Innovation #8
# ──────────────────────────────────────────────

class MemRLEngine:
    """
    Aegis Zero's self-evolution engine.

    Three public methods used by the rest of the stack:

    1. retrieve(query)
       → Two-Phase retrieval: semantic filter + Q-value re-rank
       → Called by ContextEngine.build() instead of passive RAG

    2. record_feedback(episode_id, reward_type, ...)
       → Receives a signal, updates Q-value via EMA
       → Called by: Auditor (after review), MemoryWriter (after outcome)

    3. batch_update(hours_back=24)
       → Nightly pipeline: sweeps all episodes, applies delayed rewards
       → Run at 02:00 by nightly.sh, after MemoryConsolidator

    The LLM (Gemma 4 26B/E4B) is NEVER modified.
    Only the Q-values in Qdrant evolve.
    """

    COLLECTION = "conversations"

    def __init__(self):
        self.qdrant = QdrantClient(host=get_qdrant_host(), port=get_qdrant_port())

    def _embed(self, text: str) -> list[float]:
        resp = ollama.embeddings(model=get_embed_model(), prompt=text)
        return resp["embedding"]

    # ── TWO-PHASE RETRIEVAL ──────────────────────

    def retrieve(self, query: str,
                 k1: int = K1, k2: int = K2,
                 min_similarity: float = SIMILARITY_THRESHOLD
                 ) -> list[RetrievalResult]:
        """
        Two-Phase Retrieval: the MemRL upgrade to passive semantic search.

        Phase A: Retrieve top-k1 episodes by cosine similarity.
                 (Identical to existing ContextEngine — but a larger pool)

        Phase B: From the k1 candidates, select top-k2 by Q-value.
                 High-Q memories are promoted. Low-Q noise is suppressed.

        Returns: top-k2 results, ordered by combined score.
        """
        try:
            query_vector = self._embed(query)
        except Exception:
            return []

        # ── Phase A: Semantic recall ──────────────
        try:
            phase_a_hits = self.qdrant.search(
                collection_name=self.COLLECTION,
                query_vector=query_vector,
                limit=k1,
                score_threshold=min_similarity,
                with_payload=True
            )
        except Exception:
            return []

        if not phase_a_hits:
            return []

        # Increment retrieval_count for all Phase A candidates
        self._increment_retrieval_counts([h.id for h in phase_a_hits])

        # ── Phase B: Q-value re-ranking ───────────
        candidates = []
        for rank_a, hit in enumerate(phase_a_hits, 1):
            payload = hit.payload
            if payload.get("layer") != "episodic":
                continue

            q_value = float(payload.get("q_value", Q_INIT))
            similarity = float(hit.score)

            # Combined score: blend similarity and Q-value
            # α=0.4 semantic + β=0.6 Q-value
            # (Q-value weighted more — the whole point of MemRL)
            combined = 0.4 * similarity + 0.6 * q_value

            candidates.append(RetrievalResult(
                episode_id=str(hit.id),
                experience=payload.get("summary", ""),
                intent_text=payload.get("intent_text", payload.get("summary", "")[:100]),
                q_value=q_value,
                similarity=similarity,
                phase_a_rank=rank_a,
                phase_b_rank=0,  # Set below
                combined_score=combined
            ))

        # Sort by combined score, take top-k2
        candidates.sort(key=lambda c: c.combined_score, reverse=True)
        top_k2 = candidates[:k2]

        for rank_b, c in enumerate(top_k2, 1):
            c.phase_b_rank = rank_b

        # Increment selection_count for Phase B survivors
        self._increment_selection_counts([c.episode_id for c in top_k2])

        return top_k2

    def _increment_retrieval_counts(self, episode_ids: list[str]) -> None:
        """Increment retrieval_count for Phase A hits (background tracking)."""
        try:
            for ep_id in episode_ids:
                # Fetch current count and increment
                result = self.qdrant.retrieve(
                    collection_name=self.COLLECTION,
                    ids=[ep_id],
                    with_payload=True
                )
                if result:
                    current = result[0].payload.get("retrieval_count", 0)
                    self.qdrant.set_payload(
                        collection_name=self.COLLECTION,
                        payload={"retrieval_count": current + 1},
                        points=[ep_id]
                    )
        except Exception:
            pass  # Tracking failures never block retrieval

    def _increment_selection_counts(self, episode_ids: list[str]) -> None:
        """Increment selection_count for Phase B survivors."""
        try:
            for ep_id in episode_ids:
                result = self.qdrant.retrieve(
                    collection_name=self.COLLECTION,
                    ids=[ep_id],
                    with_payload=True
                )
                if result:
                    current = result[0].payload.get("selection_count", 0)
                    self.qdrant.set_payload(
                        collection_name=self.COLLECTION,
                        payload={"selection_count": current + 1},
                        points=[ep_id]
                    )
        except Exception:
            pass

    # ── Q-VALUE UPDATE ───────────────────────────

    def record_feedback(self, episode_id: str,
                        reward_type: str,
                        source: str = "unknown",
                        task_id: str = "") -> Optional[float]:
        """
        Record a feedback signal and update Q-value via EMA.

        Q_new = α * reward + (1 - α) * Q_old

        Called immediately after:
        - Auditor runs (source="auditor")
        - MemoryWriter writes outcome (source="outcome")
        - User sends a correction (source="user_correction")
        - Conversation continues (source="continuation")

        Returns: new Q-value, or None if episode not found.
        """
        reward = REWARDS.get(reward_type, REWARDS["no_signal"])

        try:
            result = self.qdrant.retrieve(
                collection_name=self.COLLECTION,
                ids=[episode_id],
                with_payload=True
            )
            if not result:
                return None

            payload = result[0].payload
            q_old = float(payload.get("q_value", Q_INIT))
            reward_history = payload.get("reward_history", [])

            # EMA update — the core MemRL Q-value update rule
            q_new = Q_ALPHA * reward + (1 - Q_ALPHA) * q_old
            q_new = max(Q_MIN, min(Q_MAX, q_new))  # Clamp to [0.01, 0.99]

            reward_history.append(round(reward, 3))
            reward_history = reward_history[-20:]  # Keep last 20 signals

            self.qdrant.set_payload(
                collection_name=self.COLLECTION,
                payload={
                    "q_value": round(q_new, 4),
                    "reward_history": reward_history,
                    "last_rewarded": datetime.now(timezone.utc).isoformat(),
                    "last_reward_source": source,
                    "last_reward_type": reward_type
                },
                points=[episode_id]
            )
            return q_new

        except Exception:
            return None

    # ── IMPLICIT REWARD DETECTION ────────────────

    def detect_reward_from_auditor(self, auditor_output: str,
                                   episode_id: str,
                                   task_id: str = "") -> Optional[float]:
        """
        Extract reward signal from Auditor output JSON.
        Called automatically after every Auditor run.
        """
        try:
            data = json.loads(auditor_output)
            confidence = float(data.get("confidence", 0.5))
            approved = data.get("approved", True)
            issues = data.get("issues", [])

            if not approved or issues:
                reward_type = "auditor_revised"
            elif confidence > 0.85:
                reward_type = "auditor_approved_high"
            else:
                reward_type = "auditor_approved"

            return self.record_feedback(
                episode_id=episode_id,
                reward_type=reward_type,
                source="auditor",
                task_id=task_id
            )
        except (json.JSONDecodeError, ValueError):
            return None

    def detect_reward_from_message(self, user_message: str,
                                   prev_episode_id: str,
                                   task_id: str = "") -> Optional[float]:
        """
        Detect implicit reward from the user's next message.
        Corrections are negative evidence. Generic follow-ups are too ambiguous
        to reward automatically and default to no-signal.
        Called when user sends their next message.
        """
        lower = user_message.lower()

        if any(kw in lower for kw in CORRECTION_KEYWORDS):
            reward_type = "user_correction"
        else:
            reward_type = "no_signal"

        return self.record_feedback(
            episode_id=prev_episode_id,
            reward_type=reward_type,
            source="user_continuation",
            task_id=task_id
        )

    def detect_reward_from_outcome(self, episode_outcome: str,
                                   episode_id: str,
                                   task_id: str = "") -> Optional[float]:
        """
        Map episode outcome to reward. Called by MemoryWriter after compression.
        """
        outcome_rewards = {
            "resolved":  "task_resolved",
            "ongoing":   "task_ongoing",
            "abandoned": "task_abandoned",
            "deferred":  "task_ongoing"
        }
        reward_type = outcome_rewards.get(episode_outcome, "no_signal")
        return self.record_feedback(
            episode_id=episode_id,
            reward_type=reward_type,
            source="outcome",
            task_id=task_id
        )

    # ── BATCH UPDATE (NIGHTLY) ───────────────────

    def batch_update(self, max_episodes: int = 200) -> dict:
        """
        Nightly batch Q-value sweep.
        Finds episodes missing Q-values and initialises them.
        Finds episodes with accumulated rewards and stabilises their Q-values.
        Finds low-utility memories and marks them for pruning.

        Run at 02:10 by nightly.sh (after memory consolidation).
        """
        t0 = time.time()
        result = {
            "initialised": 0,
            "updated": 0,
            "pruned": 0,
            "high_utility": 0,   # Q > 0.80
            "low_utility": 0,    # Q < 0.20
            "duration_sec": 0.0
        }

        try:
            scroll_result = self.qdrant.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=Filter(must=[
                    FieldCondition(key="layer", match=MatchValue(value="episodic"))
                ]),
                limit=max_episodes,
                with_payload=True
            )
            episodes = scroll_result[0]
        except Exception as e:
            result["error"] = str(e)
            result["duration_sec"] = round(time.time() - t0, 2)
            return result

        for ep in episodes:
            payload = ep.payload
            q_value = payload.get("q_value")

            # Initialise missing Q-values
            if q_value is None:
                outcome = payload.get("outcome", "ongoing")
                initial_reward = REWARDS.get(
                    f"task_{outcome}", REWARDS["no_signal"]
                )
                q_init = Q_ALPHA * initial_reward + (1 - Q_ALPHA) * Q_INIT
                try:
                    self.qdrant.set_payload(
                        collection_name=self.COLLECTION,
                        payload={
                            "q_value": round(q_init, 4),
                            "reward_history": [round(initial_reward, 3)],
                            "retrieval_count": 0,
                            "selection_count": 0,
                            "memrl_version": "1.0"
                        },
                        points=[ep.id]
                    )
                    result["initialised"] += 1
                except Exception:
                    pass
                continue

            q_value = float(q_value)

            # Track high/low utility
            if q_value > 0.80:
                result["high_utility"] += 1
            elif q_value < 0.20:
                result["low_utility"] += 1

            # Prune very low-Q, stale memories
            # (Q < 0.10 AND older than 30 days AND never selected in Phase B)
            selection_count = payload.get("selection_count", 0)
            timestamp = payload.get("timestamp", "")
            is_stale = self._is_stale(timestamp, days=30)

            if q_value < 0.10 and is_stale and selection_count == 0:
                try:
                    # Mark for pruning — don't delete immediately
                    # (deletion is irreversible; marking allows review)
                    self.qdrant.set_payload(
                        collection_name=self.COLLECTION,
                        payload={"pruning_candidate": True,
                                 "pruning_reason": "low_q_stale_unselected"},
                        points=[ep.id]
                    )
                    result["pruned"] += 1
                except Exception:
                    pass
            else:
                result["updated"] += 1

        result["duration_sec"] = round(time.time() - t0, 2)
        return result

    def _is_stale(self, timestamp_str: str, days: int = 30) -> bool:
        """Check if an episode is older than `days` days."""
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return (now - ts).days > days
        except Exception:
            return False

    # ── ANALYTICS ───────────────────────────────

    def get_memory_health(self) -> dict:
        """
        Summary of MemRL state — sent in nightly Telegram report.
        Shows Q-value distribution, pruning candidates, top memories.
        """
        try:
            scroll_result = self.qdrant.scroll(
                collection_name=self.COLLECTION,
                scroll_filter=Filter(must=[
                    FieldCondition(key="layer", match=MatchValue(value="episodic"))
                ]),
                limit=500,
                with_payload=True
            )
            episodes = scroll_result[0]
        except Exception:
            return {"error": "qdrant_unavailable"}

        if not episodes:
            return {"total": 0, "message": "No episodic memories yet"}

        q_values = [float(ep.payload.get("q_value", Q_INIT)) for ep in episodes]
        total = len(q_values)

        return {
            "total_memories": total,
            "q_distribution": {
                "high_0.80+":  sum(1 for q in q_values if q >= 0.80),
                "good_0.60+":  sum(1 for q in q_values if 0.60 <= q < 0.80),
                "neutral_0.40+": sum(1 for q in q_values if 0.40 <= q < 0.60),
                "poor_0.20+":  sum(1 for q in q_values if 0.20 <= q < 0.40),
                "low_0.20-":   sum(1 for q in q_values if q < 0.20),
            },
            "mean_q": round(sum(q_values) / total, 3),
            "pruning_candidates": sum(
                1 for ep in episodes
                if ep.payload.get("pruning_candidate", False)
            ),
            "memrl_coverage": sum(
                1 for ep in episodes
                if ep.payload.get("q_value") is not None
            ) / total,
        }


# ──────────────────────────────────────────────
# UPGRADED CONTEXT ENGINE INTEGRATION
# Replaces passive semantic search with Two-Phase Retrieval
# ──────────────────────────────────────────────

class MemRLContextRetriever:
    """
    Drop-in replacement for ContextEngine.get_recent_episodes().

    BEFORE (passive):
        hits = qdrant.search(collection, query_vector, limit=4)
        → Returns most semantically similar episodes
        → No quality signal. Noise retrieved alongside signal.

    AFTER (MemRL):
        results = memrl.retrieve(query, k1=20, k2=4)
        → Phase A: top-20 by similarity
        → Phase B: top-4 by Q-value from Phase A pool
        → Only high-utility experiences reach the context window
    """

    def __init__(self):
        self.memrl = MemRLEngine()

    def get_episodes(self, query: str,
                     limit: int = 4) -> list[dict]:
        """
        Replacement for ContextEngine.get_recent_episodes().
        Returns top-limit episodes via Two-Phase Retrieval.
        """
        results = self.memrl.retrieve(query, k1=K1, k2=limit)

        return [
            {
                "summary":     r.experience,
                "topics":      [],
                "outcome":     "unknown",
                "timestamp":   "",
                "relevance":   round(r.combined_score, 3),
                "q_value":     round(r.q_value, 3),
                "phase_b_rank": r.phase_b_rank,
                "episode_id":  r.episode_id,
            }
            for r in results
        ]


# ──────────────────────────────────────────────
# FEEDBACK HOOKS — wire into existing stack
# ──────────────────────────────────────────────

class MemRLFeedbackCollector:
    """
    Collects implicit reward signals from the existing pipeline.
    Wire this into HardenedPuppeteer and MemoryWriter.

    No human labelling. No explicit ratings. All signals are implicit:
    - Did the Auditor approve?
    - Did the user continue the conversation?
    - Did the user send a correction?
    - What was the episode outcome?
    """

    def __init__(self):
        self.memrl = MemRLEngine()
        self._last_episode_id: Optional[str] = None

    def on_episode_written(self, episode_id: str,
                           outcome: str,
                           task_id: str = "") -> None:
        """
        Called by MemoryWriter.write_turn() after episode is stored.
        Records outcome-based reward immediately.
        """
        self._last_episode_id = episode_id
        self.memrl.detect_reward_from_outcome(outcome, episode_id, task_id)

    def on_auditor_complete(self, episode_id: str,
                            auditor_output: str,
                            task_id: str = "") -> None:
        """
        Called by AuditorPuppet after review.
        Extracts reward from approval/confidence/issues.
        """
        self.memrl.detect_reward_from_auditor(
            auditor_output, episode_id, task_id
        )

    def on_user_message(self, user_message: str,
                        task_id: str = "") -> None:
        """
        Called at the START of each new user message.
        The previous episode gets a reward based on whether
        the user continued (positive) or corrected (negative).
        """
        if self._last_episode_id:
            self.memrl.detect_reward_from_message(
                user_message,
                self._last_episode_id,
                task_id
            )


# ──────────────────────────────────────────────
# NIGHTLY PIPELINE ADDITION
# Adds to existing run_nightly_pipeline() in context_engine.py
# ──────────────────────────────────────────────

def run_memrl_nightly(send_telegram: bool = True) -> dict:
    """
    MemRL nightly maintenance run.
    Add to nightly.sh after context_engine.py consolidate:
      python3 ~/.aegis/memrl/memrl_engine.py nightly

    Steps:
    1. Batch Q-value initialisation for new episodes
    2. Prune candidate marking for low-utility stale memories
    3. Generate health report
    4. Telegram report (silent)
    """
    import os, httpx

    engine = MemRLEngine()

    # Step 1+2: Batch update
    update_result = engine.batch_update()

    # Step 3: Health snapshot
    health = engine.get_memory_health()

    # Step 4: Telegram report
    if send_telegram:
        bot_token = get_telegram_bot_token()
        chat_id = get_telegram_chat_id()
        if bot_token and chat_id:
            dist = health.get("q_distribution", {})
            msg = (
                f"🧬 *MemRL Nightly Report*\n\n"
                f"Total memories: `{health.get('total_memories', 0)}`\n"
                f"Mean Q-value: `{health.get('mean_q', 0):.3f}`\n"
                f"High utility (Q≥0.8): `{dist.get('high_0.80+', 0)}`\n"
                f"Low utility (Q<0.2): `{dist.get('low_0.20-', 0)}`\n"
                f"Pruning candidates: `{health.get('pruning_candidates', 0)}`\n"
                f"MemRL coverage: `{health.get('memrl_coverage', 0):.0%}`\n"
                f"Initialised: `{update_result.get('initialised', 0)}`\n"
                f"Duration: `{update_result.get('duration_sec', 0)}s`"
            )
            try:
                httpx.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg,
                          "parse_mode": "Markdown",
                          "disable_notification": True},
                    timeout=10
                )
            except Exception:
                pass

    return {
        "batch_update": update_result,
        "health": health,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ──────────────────────────────────────────────
# WIRING SUMMARY
# Exact changes to existing files
# ──────────────────────────────────────────────
#
# 1. context_engine.py — replace get_recent_episodes():
#
#    # ADD at top:
#    from memrl.memrl_engine import MemRLContextRetriever
#    _memrl_retriever = MemRLContextRetriever()
#
#    # REPLACE ContextEngine.get_recent_episodes():
#    def get_recent_episodes(self, message, limit=4, recency_hours=168):
#        return _memrl_retriever.get_episodes(message, limit=limit)
#
# 2. context_engine.py — MemoryWriter.write_turn():
#
#    # ADD after episode is written:
#    from memrl.memrl_engine import MemRLFeedbackCollector
#    _feedback = MemRLFeedbackCollector()
#    _feedback.on_episode_written(ep_id, episode.outcome, task_id)
#
# 3. puppeteer.py — AuditorPuppet.run():
#
#    # ADD after auditor result parsed:
#    from memrl.memrl_engine import MemRLFeedbackCollector
#    _feedback.on_auditor_complete(last_episode_id, result.output, task_id)
#
# 4. agent_harness.py — HardenedPuppeteer.run():
#
#    # ADD at START of run(), before classification:
#    from memrl.memrl_engine import MemRLFeedbackCollector
#    _feedback.on_user_message(message, task_id)
#
# 5. nightly.sh — ADD after context_engine consolidate:
#
#    python3 ~/.aegis/memrl/memrl_engine.py nightly >> "$LOG" 2>&1
#
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "nightly":
        result = run_memrl_nightly()
        print(json.dumps(result, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "health":
        engine = MemRLEngine()
        health = engine.get_memory_health()
        print(json.dumps(health, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        # Quick smoke test
        engine = MemRLEngine()
        print("Testing Two-Phase Retrieval...")
        results = engine.retrieve("debug Python KeyError", k1=10, k2=3)
        print(f"Retrieved {len(results)} results")
        for r in results:
            print(f"  Q={r.q_value:.3f} sim={r.similarity:.3f} combined={r.combined_score:.3f}")
            print(f"  '{r.experience[:60]}...'")
        print("\nMemRL engine operational.")

    else:
        engine = MemRLEngine()
        health = engine.get_memory_health()
        print(f"MemRL Engine v1.0")
        print(f"Memories: {health.get('total_memories', 0)}")
        print(f"Mean Q: {health.get('mean_q', 'N/A')}")
        print(f"Coverage: {health.get('memrl_coverage', 0):.0%}")
        print("\nCommands: nightly | health | test")
