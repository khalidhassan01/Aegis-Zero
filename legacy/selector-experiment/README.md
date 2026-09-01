# Legacy: the in-repo model-selector experiment (2026-08-31)

Status: **superseded — preserved for reference, not shipped.**

This was an experiment to build the automatic free-model selector *inside*
Aegis Zero as a `provider.kind: selector` provider: a key pool
(`keys.py`), a live free-model catalog (`catalog.py`), benchmark priors
(`benchmarks.py`), per-(key, model) learning (`learning.py`), routing with
rate-limit benching and fail-over (`router.py`, `shield.py`), all behind
`SelectorProvider` (`provider.py`).

**Why it is here and not in `src/`:** the production implementation shipped
first in Khalid's Telegram gateway (`telegram-gateway/selector/`, gateway
v3) — built, tested, and running against live traffic before this in-repo
version was finished. This copy never gained its own test suite and was
never part of a verified release, so it is archived out of the shipped
package rather than committed half-tested into a release that advertises
"test-backed claims only".

**Contents**

- `src/` — the nine experiment modules, exactly as they stood.
- `src-integration.patch` — the (reverted) changes that wired them into
  `app.py`, `cli.py`, `core/config.py`, `core/errors.py`,
  `providers/__init__.py`, and `providers/openai_compat.py`. The patch also
  contains independently useful provider hardening (typed 401/402/403
  auth errors, `Retry-After` parsing) that a future 2.x may want to
  resurrect deliberately, *with tests*.

**To resurrect any of it:** apply the patch, restore `src/aegis_zero/selector/`
from `src/`, and add the missing test coverage before it ships.
