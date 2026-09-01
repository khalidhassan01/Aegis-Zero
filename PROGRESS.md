# Aegis-Zero — Progress Snapshot (RESUMABLE)
Generated: 2026-09-01 09:50 +02:00 (Rafiq, virality-push job)
Branch: v2-rebuild   HEAD: 6ff773c   Tag: v2.0.0 → a15f1fc (local only)
Pushed to origin: NO — origin tip is 072b6ae. Push ONLY when Khalid
explicitly asks. (The release commits b1abaf5/5181bad/a15f1fc/6ff773c
are local; PyPI does not need the push.)

===============================================================
1. CURRENT MISSION — the virality push, step 1: PyPI publish
===============================================================
State: EVERYTHING is built, verified, and staged. The ONLY missing
piece is a PyPI API token (Khalid's to create — it does not exist on
this machine; checked env, ~/.pypirc, vault backups, whole workspace).

Release contents (all committed):
- b1abaf5  demo work: examples/demo.py, scripts/make_demo.py,
  docs/demo.svg + docs/demo.cast, tests/test_demo_assets.py, README
  (PyPI badge + "Watch it work" + pip install aegis-zero)
- 5181bad  CHANGELOG: [Unreleased] folded into [2.0.0] - 2026-09-01
  (no tag/release ever existed, so 2.0.0 is the first release; 325→326
  tests, honest "179 at rebuild time (325 today)" note)
- a15f1fc  fix: examples/custom_tools.py double-await crash (pre-
  existing, crashed on EVERY run), tests/test_offline_examples.py
  smoke-pins demo+offline_testing, ruff-format all examples
- 6ff773c  scripts/publish-pypi.sh (token-gated upload + live verify)

Verification (fresh venvs, from the built artifacts — see
dist/verify-2.0.0.log, commit a15f1fc):
- twine check: sdist + wheel PASSED
- sdist installed into fresh venv → full suite: 326 passed
  (needs qdrant extra for the 5 qdrant tests — optional-dependency,
  not a code failure)
- wheel installed into fresh venv → aegis --version/--help OK,
  demo.py / offline_testing.py / custom_tools.py all run clean
- ruff check OK · ruff format --check OK (src tests examples scripts)
  · mypy OK (32 files)
- wheel: 37 files, NO selector WIP inside; METADATA carries version
  2.0.0, PyPI badge, Watch-it-work section
- secret scan of sdist: clean (legacy token refs are env-var reads)
- artifacts staged in dist/ + hashes logged:
  wheel  sha256 bf65c7274862cb1dec22faeaf023e34ef3364b23382ea1b0344efde18c1cbc3d
  sdist  sha256 71b146d159202080aeaba2939a3fb6c07e7548c7e0d78a9c2ed9b7320ddfa53d
- PyPI name check: JSON API 404 → "aegis-zero" has NO releases.
  Whether the name is registered-but-empty by someone else can only be
  learned at upload time (403 = taken; then stop, do not retry).

THE ONE REMAINING STEP (needs Khalid, ~2 min):
1. pypi.org → log in → Account settings → API tokens → Add token,
   scope "Entire account" (project scope needs the project to exist).
2. Then either paste the token to Rafiq on Telegram, or run:
      PYPI_TOKEN='pypi-…' ./scripts/publish-pypi.sh
   The script uploads, waits for the index, installs from the LIVE
   index into a fresh venv, and runs the offline demo. Token is never
   stored on disk.
   (If Rafiq runs it inside the agent sandbox: export
   UV_CACHE_DIR=/home/khalid/Projekte/.aegis-build-tools/uv-cache first.)

Build/verify environment (reusable, kept out of the repo):
- /home/khalid/Projekte/.aegis-release     git worktree @ a15f1fc
- /home/khalid/Projekte/.aegis-build-tools/{uv-cache,relenv,wheelenv,twineenv}
  (NOTE: /tmp is EPHEMERAL per shell call on this box — do not build
  or place venvs there.)

===============================================================
2. UNCOMMITTED ON TOP (Khalid's WIP — deliberately untouched)
===============================================================
- src/aegis_zero/selector/* + src changes in app.py, cli.py,
  core/config.py, core/errors.py, providers/__init__.py,
  providers/openai_compat.py — the in-Aegis model-selector experiment
  (2026-08-31 evening). NOT part of 2.0.0 (no tests of its own); the
  production selector for Khalid's Telegram setup lives in
  telegram-gateway/selector/ instead. Decide its fate before any 2.1.

===============================================================
3. CITATIONS (unchanged)
===============================================================
All 21 arXiv citations verified live earlier; list in
docs/AEGIS_ZERO_RESEARCH_FOUNDATION.md (11) + docs/ROADMAP.md (14).
Do not re-verify unless docs change. README carries none.

===============================================================
4. OPEN / NEXT (honest)
===============================================================
- PyPI upload (token-gated, see above) — then README badge goes live.
- Virality step 2: 30s video/asciinema capture for socials
  (docs/demo.cast exists; a GIF/MP4 for X/Reddit/HN does not).
- Virality step 3: announce (Show HN, r/LocalLLaMA, X thread).
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
- Commit as khalidhassan01 <khalidhassan01@gmail.com>.
