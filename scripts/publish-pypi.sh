#!/usr/bin/env bash
# Publish aegis-zero to PyPI, then verify the live index actually serves it.
#
# Usage:
#   PYPI_TOKEN='pypi-AgEIcH…' ./scripts/publish-pypi.sh
#   ./scripts/publish-pypi.sh 'pypi-AgEIcH…'
#
# The token is read ONLY from the argument or the environment — it is never
# written to disk or into git. Create it at pypi.org → Account settings →
# API tokens → "Add API token", scope "Entire account" (a project-scoped
# token requires the project to already exist; this is the first release).
#
# If PyPI answers 403 "not allowed to upload to project 'aegis-zero'", the
# name is taken by another account — stop and reassess (rename or contact
# PyPI support); do not retry.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="2.0.0"
FILES=(dist/aegis_zero-${VERSION}.tar.gz dist/aegis_zero-${VERSION}-py3-none-any.whl)
TOKEN="${1:-${PYPI_TOKEN:-}}"

fail() { echo "publish-pypi: $*" >&2; exit 1; }

for f in "${FILES[@]}"; do
  [[ -f "$f" ]] || fail "missing $f — build first: uv build"
done
if [[ -z "$TOKEN" ]]; then
  fail "no token given. Run: PYPI_TOKEN='pypi-…' $0
  (create it at pypi.org → Account settings → API tokens → Add token, scope: Entire account)"
fi

echo "==> uploading ${FILES[*]} to PyPI"
uv publish --token "$TOKEN" "${FILES[@]}"

echo "==> waiting for the index to serve the release (up to 5 min)"
code=000
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://pypi.org/pypi/aegis-zero/${VERSION}/json" || true)
  [[ "$code" == "200" ]] && break
  sleep 10
done
[[ "$code" == "200" ]] || fail "release not visible yet (last HTTP $code) — check https://pypi.org/project/aegis-zero/ in a few minutes"

echo "==> fresh-venv install from the LIVE index + offline engine run"
VENV="$(mktemp -d)/verify-venv"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet "aegis-zero==${VERSION}"
"$VENV/bin/aegis" --version
"$VENV/bin/python" examples/demo.py > /dev/null
echo "live install verified: aegis-zero ${VERSION} installs from PyPI and runs offline"

echo
echo "✅ aegis-zero ${VERSION} is live: https://pypi.org/project/aegis-zero/"
echo "Next (virality steps 2–3): capture the demo for socials, then announce."
