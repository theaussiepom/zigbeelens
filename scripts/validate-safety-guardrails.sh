#!/usr/bin/env bash
# Run the release safety owner and fail if any test is skipped.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -n "${CORE_PYTHON:-}" ]]; then
  PYTHON="${CORE_PYTHON}"
elif [[ -x "${ROOT}/apps/core/.venv/bin/python" ]]; then
  PYTHON="${ROOT}/apps/core/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1 \
  && python3 -c 'import pytest' >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "validate-safety-guardrails.sh: Core pytest environment is unavailable" >&2
  exit 1
fi

RESULT="$(mktemp "${TMPDIR:-/tmp}/zigbeelens-safety.XXXXXX")"
cleanup() {
  rm -f "${RESULT}"
}
trap cleanup EXIT

(
  cd "${ROOT}/apps/core"
  export PYTHONPATH="${ROOT}/apps/core/src${PYTHONPATH:+:${PYTHONPATH}}"
  "${PYTHON}" -m pytest \
    -q tests/test_safety_guardrails.py -ra \
    --junitxml="${RESULT}"
)

"${PYTHON}" - "${RESULT}" <<'PY'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
tests = sum(int(suite.get("tests", "0")) for suite in suites)
skipped = sum(int(suite.get("skipped", "0")) for suite in suites)
failures = sum(int(suite.get("failures", "0")) for suite in suites)
errors = sum(int(suite.get("errors", "0")) for suite in suites)

if tests == 0:
    raise SystemExit("Safety guardrail owner collected zero tests")
if skipped:
    raise SystemExit(f"Safety guardrail owner skipped {skipped} test(s)")
if failures or errors:
    raise SystemExit(
        f"Safety guardrail owner recorded {failures} failure(s) and {errors} error(s)"
    )
print(f"Safety guardrail ownership OK: {tests} tests, 0 skipped.")
PY
