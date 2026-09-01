# Aegis-Zero — Progress Snapshot (RESUMABLE)
Generated: 2026-09-01 11:10 +02:00 (Rafiq, virality-push job, step 2)
Branch: v2-rebuild   HEAD: f98a123 (step-2 video commit)
Tag: v2.0.0 → a15f1fc (local only; dist/ artifacts verified against it)
Pushed to origin: NO — origin tip is 072b6ae. Push ONLY when Khalid
explicitly asks. (PyPI does not need the push.)

===============================================================
1. VIRALITY PUSH — state of the three steps
===============================================================
STEP 1 — PyPI publish: built, verified, staged; ONLY missing a PyPI API
token (Khalid's 2-min part — none exists on this machine; checked env,
~/.pypirc, vault backups, workspace). Resume instructions:
  1. pypi.org → Account settings → API tokens → Add (scope: Entire account)
  2. PYPI_TOKEN='pypi-…' ./scripts/publish-pypi.sh   (uploads, waits for
     the index, installs from LIVE PyPI into a fresh venv, runs the demo;
     token never stored on disk; 403 = name taken → stop and reassess)
  Release detail (commits b1abaf5/5181bad/a15f1fc/6ff773c, verification
  log dist/verify-2.0.0.log, artifact sha256s) unchanged and still valid.

STEP 2 — socials video: DONE 2026-09-01, commit f98a123. Shipped:
  - docs/demo.mp4        864 KB  h264 yuv420p 1920x1080 30fps, 33.8 s
                          (30 s demo + branded end card: logo, install
                          chip, repo link, tagline), faststart, silent
  - docs/demo.gif       1.77 MB  960x540 15fps palette GIF (READMEs/chat)
  - docs/demo-poster.png        full-transcript frame for thumbnails
  - docs/demo.video.json        manifest: sha256+bytes of all three,
                          timeline, frame spec, fonts, tool versions
  Generator: scripts/make_video.py (Pillow + ffmpeg; --check verifies
  hashes without Pillow; --probe OUT.png --at S inspects one frame).
  Timeline inherited from make_demo.schedule() — cast, SVG and video can
  never disagree; tests/test_demo_video.py pins it (6 tests; PIL probes
  skip gracefully in envs without Pillow — proven in a fresh wheel venv).
  Deterministic: re-render after formatting was bit-identical.
  Verification evidence: dist/video-2.0.0.log (encode fidelity, 72-check
  pixel audit, gates). Regenerate after code changes:
      python scripts/make_video.py   (then re-run pytest)
  Logo raster input: Logo-Designs/aegis-zero-logo.png (ffmpeg one-liner
  in make_video.py docstring).

STEP 3 — announce (Show HN, r/LocalLLaMA, X thread): NOT started. Wants,
  in order: PyPI token (step 1), origin push (Khalid's explicit ask),
  then the posts themselves. The MP4 is the attach-ready asset.

===============================================================
2. UNCOMMITTED ON TOP (Khalid's WIP — deliberately untouched)
===============================================================
- src/aegis_zero/selector/* + src changes in app.py, cli.py,
  core/config.py, core/errors.py, providers/__init__.py,
  providers/openai_compat.py — the in-Aegis model-selector experiment
  (2026-08-31 evening). NOT part of 2.0.0 (no tests of its own); the
  production selector for Khalid's Telegram setup lives in
  telegram-gateway/selector/ instead. Decide its fate before any 2.1.
  (Verified during step 2: this WIP does NOT drift the demo transcript —
  it still matches the pinned cast byte-for-byte.)

===============================================================
3. CITATIONS (unchanged)
===============================================================
All 21 arXiv citations verified live earlier; list in
docs/AEGIS_ZERO_RESEARCH_FOUNDATION.md (11) + docs/ROADMAP.md (14).
Do not re-verify unless docs change. README carries none.

===============================================================
4. OPEN / NEXT (honest)
===============================================================
- PyPI upload (token-gated, see step 1) — then README badge goes live.
- Virality step 3: announce (Show HN, r/LocalLLaMA, X thread) after
  upload + push.
- Push v2-rebuild + tag to GitHub when Khalid says so (repo README
  links there; announce wants the repo public and current).
- Phase-3 eval harness still the biggest open research item (not
  claimed anywhere as done).

===============================================================
5. DO NOT
===============================================================
- Do NOT push to origin unless Khalid explicitly asks.
- Do NOT edit any arXiv citation that already resolves.
- Do NOT claim the Phase-3 eval exists; it does NOT.
- Do NOT re-run make_demo.py expecting different output — assets are
  pinned by tests; regenerate only via the script after code changes.
  (Same rule for make_video.py: regenerate, never hand-edit binaries.)
- Commit as khalidhassan01 <khalidhassan01@gmail.com>.
