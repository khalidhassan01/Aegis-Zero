# Aegis-Zero — Progress Snapshot (FINAL — repo finalized on GitHub)
Updated: 2026-09-01 (Rafiq, finalization pass)
Branch: v2-rebuild — fully pushed, working tree clean.
PR #1 (v2-rebuild → main): merged as a clean fast-forward; main now
carries the full 2.0.0 rebuild. Full suite green at the final state:
342 passed.

## Repo state (all verified)
- v2-rebuild tip on origin == local (nothing unpushed).
- main == v2-rebuild (fast-forward merge, zero conflicts; GitHub closed
  PR #1 as merged when the commits landed on main).
- Tag v2.0.0 → 40aac59 (annotated efe66ce), identical on local and
  origin. dist/ artifacts were built and verified against exactly that
  tree. Commits after the tag (93fbfbd CodeQL/CI fix + this docs
  commit) touch CI config, tests, and docs only — no shipped code —
  so the tag deliberately stays where the verified release tree is.
  Do not move it without rebuilding + re-verifying dist/.
- CodeQL: green; legacy/** excluded from analysis via
  .github/codeql/config.yml (read-only archive, not shipped).
  The weak-hash finding on legacy's key_fingerprint was triaged as a
  false positive (fast dedup/label id, not password storage).

## Remaining — both outside the repo, both Khalid-gated
1. **PyPI upload** (token-gated; instructions preserved below).
   The PyPI version badge in the README goes live only after this.
2. **Announce** (Show HN, r/LocalLLaMA, X thread) — after the upload.
   docs/demo.mp4 (864 KB, 1080p, 33.8 s, silent) is the attach-ready
   asset; docs/demo.gif for chat contexts.
   Optional nicety: cut a GitHub Release for v2.0.0 in the web UI and
   attach dist/aegis_zero-2.0.0.tar.gz + the wheel (needs the UI or
   an API token; plain git push cannot create releases).

## PyPI resume instructions (unchanged, still valid)
1. pypi.org → Account settings → API tokens → Add (scope: Entire account)
2. PYPI_TOKEN='pypi-…' ./scripts/publish-pypi.sh
   (uploads, waits for the index, installs from LIVE PyPI into a fresh
   venv, runs the demo; token never stored on disk;
   403 = name taken → stop and reassess)
   Note: dist/ was rebuilt 2026-09-01 from the fixed tree; the old
   verification logs (dist/verify-2.0.0.log, dist/video-2.0.0.log) were
   cleaned in that rebuild — the runs themselves are recorded in the
   commit history (a15f1fc/6ff773c era) and the suite is green now.

## House rules (unchanged)
- Do not edit any arXiv citation that already resolves (list in
  docs/AEGIS_ZERO_RESEARCH_FOUNDATION.md + docs/ROADMAP.md).
- Do not claim the Phase-3 eval exists; it does not.
- Do not re-run make_demo.py / make_video.py expecting different
  output — assets are pinned by tests; regenerate only via the
  scripts after code changes, never hand-edit binaries.
- Commit as khalidhassan01 <khalidhassan01@gmail.com>.
- legacy/** is a read-only archive: never modified again.
