# Aegis-Zero — Progress Snapshot (RESUMABLE)
Generated: 2026-08-31 09:06 UTC
Branch: v2-rebuild   HEAD: cite-level attribution commit (local-only, see below)
Pushed to origin/v2-rebuild: NO — origin tip is still 25aa453; the P6
cite-level commit is local. Push ONLY when Khalid explicitly asks.
Quality gate (run fresh this session): ruff check OK · ruff format OK ·
mypy OK (32 src files) · pytest 319 passed in ~4 s · branch coverage 89%

================================================================
1. WHAT IS DONE (verified by real execution this session)
================================================================
- P6 CITE-LEVEL ATTRIBUTION — CLOSED. Two deterministic evidence channels:
  * Declared: memories render with stable tags ([m1], [m2], …); the Forge
    reply ends with "MEMORIES USED: m1, …"; parse_citations() parses it
    leniently, strips it before anything downstream sees the answer, and
    maps tags back to episode ids via ContextPacket.memory_tags.
  * Grounded: grounded_ids() detects verbatim reuse (6-word n-gram overlap
    against exactly the rendered 400-char prefix) with zero model
    cooperation.
  * Weighting: declared = full run signal; undeclared grounded reuse = half;
    unevidenced recall = nothing (not punished — absence of use is not
    evidence of harm). Tombstoned memories excluded from both channels.
  * memory.credit event on EVERY protocol run with recalled memories,
    including zero-credit cases (the P6 fine-grained-attribution metric
    needs the zeros), with an honest "applied" count.
  * EngineConfig.citation_protocol=False restores the legacy coarse reward
    as an A/B ablation switch.
  * Tests: tests/test_cite_level_attribution.py (23 tests) pins both
    channels, the weighting, the ablation, and the honest limits (unknown
    tags dropped not guessed, paraphrase not grounded, prose mention of
    "memories used" not a citation, unparseable tail = attempted).
- Earlier session's items all still hold: tombstone coherence
  (invalidated_memory_ids), mypy unblocked (numpy/qdrant stub skip), ruff
  0, all 21 arXiv citations verified live, docs honesty pass.
- uv.lock is now gitignored (env artifact; CI installs via pip).

================================================================
2. CITATIONS — all 21 verified against the live arXiv API (unchanged)
================================================================
No citation was edited this session. The verified list lives in the
previous snapshots and in the docs themselves:
  docs/AEGIS_ZERO_RESEARCH_FOUNDATION.md — 11 IDs
  docs/ROADMAP.md — 14 IDs
(README carries no arXiv IDs.) Do not re-verify unless docs change.

================================================================
3. HOW TO RESUME (exact steps — do NOT wing it)
================================================================
cd ~/Projekte/Aegis-Zero && git checkout v2-rebuild
.venv/bin/python -m pytest tests/ -q          # expect 319 passed
.venv/bin/ruff check src tests && .venv/bin/ruff format --check src tests \
  && .venv/bin/python -m mypy                 # expect all OK

================================================================
4. OPEN / NEXT ITEMS (honest, not claimed-won)
================================================================
- PHASE-3 END-TO-END EVAL HARNESS (research foundation): a real measured
  eval to back the "Proven" claims, not synthetic confidence. This is now
  the single biggest open item.
- Citation-protocol live A/B: citation_protocol on vs off against the eval
  harness once it exists (the ablation switch is built for exactly this).
- Honest limits of P6 (documented, pinned, not hidden): the declared
  channel trusts the model's report; grounding catches verbatim reuse
  only, not paraphrase.

================================================================
5. DO NOT
================================================================
- Do NOT push unless Khalid explicitly asks.
- Do NOT edit any arXiv citation that already resolves (they all do).
- Do NOT claim the Phase-3 eval exists; it does NOT.
- Commit as khalidhassan01 <khalidhassan01@gmail.com>.
