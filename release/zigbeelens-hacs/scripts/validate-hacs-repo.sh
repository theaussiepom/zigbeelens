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
  CHANGELOG.md
  .github/workflows/ci.yml
  .github/workflows/release.yml
  custom_components/zigbeelens/manifest.json
  custom_components/zigbeelens/__init__.py
  custom_components/zigbeelens/api.py
  custom_components/zigbeelens/api_token.py
  custom_components/zigbeelens/binary_sensor.py
  custom_components/zigbeelens/compatibility.py
  custom_components/zigbeelens/config_flow.py
  custom_components/zigbeelens/const.py
  custom_components/zigbeelens/coordinator.py
  custom_components/zigbeelens/core_origin.py
  custom_components/zigbeelens/diagnostics.py
  custom_components/zigbeelens/entity.py
  custom_components/zigbeelens/exceptions.py
  custom_components/zigbeelens/panel_data.py
  custom_components/zigbeelens/panel.py
  custom_components/zigbeelens/panel_embed_logic.py
  custom_components/zigbeelens/panel/zigbeelens-panel.js
  custom_components/zigbeelens/repairs.py
  custom_components/zigbeelens/sensor.py
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
manifest = json.loads((root / "custom_components/zigbeelens/manifest.json").read_text())
if manifest.get("domain") != "zigbeelens":
    sys.exit("manifest domain must be zigbeelens")
if not manifest.get("version"):
    sys.exit("manifest version required")
if manifest.get("config_flow") is not True:
    sys.exit("manifest config_flow must be true")
if manifest.get("iot_class") != "local_polling":
    sys.exit("manifest iot_class must be local_polling")
if not manifest.get("codeowners"):
    sys.exit("manifest codeowners required")
strings = json.loads((root / "custom_components/zigbeelens/strings.json").read_text())
translations = json.loads((root / "custom_components/zigbeelens/translations/en.json").read_text())
if "issues" not in strings or "incompatible_core_version" not in strings["issues"]:
    sys.exit("strings.json missing incompatible_core_version")
if "issues" not in translations or "incompatible_core_version" not in translations["issues"]:
    sys.exit("translations/en.json missing incompatible_core_version")
if strings != translations:
    sys.exit("English translation must match strings.json")
print("OK: hacs.json, manifest.json, strings.json, translations/en.json parse")
PY

if python3 - "${ROOT}/custom_components/zigbeelens" <<'PY'
import ast
import sys
from pathlib import Path

root = Path(sys.argv[1])
for path in sorted(root.rglob("*.py")):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"OK: syntax {path.name}")
PY
then
  ok "Python sources parse without writing bytecode"
else
  fail "invalid Python syntax"
fi

PANEL_JS="${ROOT}/custom_components/zigbeelens/panel/zigbeelens-panel.js"
if command -v node >/dev/null 2>&1; then
  if node --check "${PANEL_JS}"; then
    ok "node --check panel JS"
  else
    fail "invalid panel JavaScript syntax"
  fi
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

require_readme "decision_contract_version = 2"
require_readme "what needs attention now"
require_readme "canonical"
require_readme "read-only"
require_readme "fallback"
require_readme "native companion summary (default)"
require_readme "try embedded view"
require_readme "back to summary"

if grep -Eqi 'does \*\*not\*\* create per-priority or per-device-story entities|does not create per-priority or per-device-story entities' <<<"${README}"; then
  ok "README distinguishes summary entities from per-priority/device-story entities"
else
  fail "README must distinguish summary entities from unsupported per-priority/device-story entities"
fi

if grep -Eqi 'auto-embed|auto embed|opens automatically in (an )?iframe' <<<"${README}"; then
  fail "README must not claim the Core dashboard auto-embeds"
else
  ok "README does not claim automatic embedding"
fi

# Stale claims that must not appear
if grep -Eqi 'decision_contract_version[[:space:]]*=[[:space:]]*1([^0-9]|$)' <<<"${README}"; then
  fail "README must not advertise decision contract v1"
else
  ok "README omits decision contract v1"
fi
if grep -Eqi 'same-protocol auto-embed|same protocol auto-embed' <<<"${README}"; then
  fail "README must not document stale same-protocol auto-embed behavior"
else
  ok "README omits stale same-protocol auto-embed behavior"
fi

if grep -RniE 'password\s*=\s*["\x27][^"\x27]{8,}|api_key\s*=\s*["\x27]|hunter2|secret-pass' "${ROOT}/custom_components" 2>/dev/null; then
  fail "possible secret in custom_components"
else
  ok "no obvious secrets in custom_components"
fi

if [[ "${FAIL}" -ne 0 ]]; then exit 1; fi
echo "HACS repo validation passed."
