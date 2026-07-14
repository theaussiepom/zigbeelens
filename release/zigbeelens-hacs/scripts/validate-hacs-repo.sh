#!/usr/bin/env bash
# Validate HACS repository layout (run from packaged repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

fail() { echo "FAIL: $1" >&2; FAIL=1; }
ok() { echo "OK: $1"; }

echo "=== ZigbeeLens HACS repo validation ==="

REQUIRED=(
  hacs.json
  README.md
  LICENSE
  custom_components/zigbeelens/manifest.json
  custom_components/zigbeelens/__init__.py
  custom_components/zigbeelens/api.py
  custom_components/zigbeelens/compatibility.py
  custom_components/zigbeelens/coordinator.py
  custom_components/zigbeelens/diagnostics.py
  custom_components/zigbeelens/panel_data.py
  custom_components/zigbeelens/panel.py
  custom_components/zigbeelens/panel/zigbeelens-panel.js
  custom_components/zigbeelens/repairs.py
  custom_components/zigbeelens/strings.json
  custom_components/zigbeelens/translations/en.json
  custom_components/zigbeelens/brand/icon.png
  custom_components/zigbeelens/brand/logo.png
  custom_components/zigbeelens/brand/icon@2x.png
  custom_components/zigbeelens/brand/logo@2x.png
)

for f in "${REQUIRED[@]}"; do
  if [[ -f "${ROOT}/${f}" ]]; then ok "$f"; else fail "missing $f"; fi
done

python3 - <<PY
import json, sys
from pathlib import Path

root = Path("${ROOT}")
hacs = json.loads((root / "hacs.json").read_text())
if hacs.get("content_in_root") is not False:
    sys.exit("hacs.json content_in_root must be false for custom_components layout")
if hacs.get("filename") != "zigbeelens":
    sys.exit("hacs.json filename must be zigbeelens")
manifest = json.loads((root / "custom_components/zigbeelens/manifest.json").read_text())
if manifest.get("domain") != "zigbeelens":
    sys.exit("manifest domain must be zigbeelens")
if not manifest.get("version"):
    sys.exit("manifest version required")
strings = json.loads((root / "custom_components/zigbeelens/strings.json").read_text())
translations = json.loads((root / "custom_components/zigbeelens/translations/en.json").read_text())
if "issues" not in strings or "incompatible_core_version" not in strings["issues"]:
    sys.exit("strings.json missing incompatible_core_version")
if "issues" not in translations or "incompatible_core_version" not in translations["issues"]:
    sys.exit("translations/en.json missing incompatible_core_version")
print("OK: hacs.json, manifest.json, strings.json, translations/en.json parse")
PY

while IFS= read -r py; do
  python3 -m py_compile "$py" && ok "syntax $(basename "$py")"
done < <(find "${ROOT}/custom_components/zigbeelens" -name '*.py' -type f)

PANEL_JS="${ROOT}/custom_components/zigbeelens/panel/zigbeelens-panel.js"
if command -v node >/dev/null 2>&1; then
  node --check "${PANEL_JS}" && ok "node --check panel JS"
else
  fail "node not available to check panel JS"
fi

README="$(tr '[:upper:]' '[:lower:]' < "${ROOT}/README.md")"
require_readme() {
  local needle="$1"
  if grep -Fqi -- "$needle" <<<"${README}"; then
    ok "README mentions: $needle"
  else
    fail "README missing required concept: $needle"
  fi
}

require_readme "decision_contract_version = 1"
require_readme "what needs attention now"
require_readme "canonical"
require_readme "read-only"
require_readme "fallback"

if grep -Eqi 'no (new )?(ha )?decision entities|does \*\*not\*\* create decision entities|does not create decision entities' <<<"${README}"; then
  ok "README documents no decision entities"
else
  fail "README must state no decision entities are created"
fi

if grep -Eqi 'auto-embed|same protocol|same-protocol' <<<"${README}"; then
  ok "README documents same-protocol auto-embed"
else
  fail "README must document same-protocol auto-embed"
fi

# Stale claims that must not appear
if grep -Eqi 'back to summary' <<<"${README}"; then
  fail "README must not claim Back to Summary"
else
  ok "README omits Back to Summary"
fi
if grep -Eqi 'native summary is always the default|always the default and does not iframe' <<<"${README}"; then
  fail "README must not claim native summary is always the default"
else
  ok "README does not claim native-only default"
fi

if grep -RniE 'password\s*=\s*["\x27][^"\x27]{8,}|api_key\s*=\s*["\x27]|hunter2|secret-pass' "${ROOT}/custom_components" 2>/dev/null; then
  fail "possible secret in custom_components"
else
  ok "no obvious secrets in custom_components"
fi

if [[ "${FAIL}" -ne 0 ]]; then exit 1; fi
echo "HACS repo validation passed."
