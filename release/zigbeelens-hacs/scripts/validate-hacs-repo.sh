#!/usr/bin/env bash
# Validate HACS repository layout (run from packaged repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

fail() { echo "FAIL: $1" >&2; FAIL=1; }
ok() { echo "OK: $1"; }

echo "=== ZigbeeLens HACS repo validation ==="

REQUIRED=(
  SOURCE_COMMIT
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

python3 - "${ROOT}" <<'PY'
import json, re, sys
from datetime import date
from pathlib import Path

root = Path(sys.argv[1])
source_commit_path = root / "SOURCE_COMMIT"
if not source_commit_path.is_file():
    sys.exit("missing SOURCE_COMMIT")
source_commit_raw = source_commit_path.read_text(encoding="utf-8")
if re.fullmatch(r"[0-9a-f]{40}\n", source_commit_raw) is None:
    sys.exit(
        "SOURCE_COMMIT must contain exactly one normalized lowercase "
        "40-character commit SHA followed by a newline"
    )
source_commit = source_commit_raw[:-1]
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
documentation = manifest.get("documentation")
documentation_match = (
    re.fullmatch(
        r"https://github\.com/"
        r"(?P<owner>[A-Za-z0-9_.-]+)/zigbeelens/blob/"
        r"(?P<commit>[0-9a-f]{40})/docs/hacs\.md",
        documentation,
    )
    if isinstance(documentation, str)
    else None
)
if documentation_match is None:
    sys.exit(
        "manifest documentation must be pinned to a normalized 40-character "
        "monorepo commit for docs/hacs.md"
    )
if documentation_match.group("commit") != source_commit:
    sys.exit(
        "manifest documentation commit does not match SOURCE_COMMIT: "
        f"{documentation_match.group('commit')} != {source_commit}"
    )
owner = documentation_match.group("owner")
readme = (root / "README.md").read_text(encoding="utf-8")
expected_commit_url = (
    f"https://github.com/{owner}/zigbeelens/commit/{source_commit}"
)
expected_commit_link = f"[`{source_commit}`]({expected_commit_url})"
local_heading = "## Local staged integration testing"
future_heading = "## Conditional public HACS installation"
local_start = readme.find(local_heading)
future_start = readme.find(future_heading)
if local_start < 0 or future_start <= local_start:
    sys.exit(
        "README must contain ordered local-stage and conditional-public-HACS sections"
    )
local_readme = readme[local_start:future_start]
if local_readme.count(expected_commit_link) != 1:
    sys.exit("README package source commit does not match SOURCE_COMMIT")
if local_readme.count(documentation) != 1:
    sys.exit(
        "README pinned documentation URL does not match manifest documentation"
    )
if "@SOURCE_COMMIT@" in readme:
    sys.exit("README contains an unresolved SOURCE_COMMIT placeholder")
reviewed_state = re.search(
    r"Reviewed public-satellite state \(historical evidence\):\s*"
    r"- commit: `(?P<commit>[0-9a-f]{40})`\s*"
    r"- reviewed: `(?P<reviewed>[0-9]{4}-[0-9]{2}-[0-9]{2})`",
    readme,
)
if reviewed_state is None:
    sys.exit(
        "README reviewed public-satellite state must include a 40-character "
        "commit SHA and ISO-format review date"
    )
try:
    date.fromisoformat(reviewed_state.group("reviewed"))
except ValueError as exc:
    raise SystemExit(
        "README public-satellite review date must be a valid ISO date"
    ) from exc
if re.search(
    r"re-check its current tree(?: immediately)? before (?:any )?publication",
    readme,
    flags=re.IGNORECASE,
) is None:
    sys.exit(
        "README must require the public satellite to be re-checked before publication"
    )
strings = json.loads((root / "custom_components/zigbeelens/strings.json").read_text())
translations = json.loads((root / "custom_components/zigbeelens/translations/en.json").read_text())
if "issues" not in strings or "incompatible_core_version" not in strings["issues"]:
    sys.exit("strings.json missing incompatible_core_version")
if "issues" not in translations or "incompatible_core_version" not in translations["issues"]:
    sys.exit("translations/en.json missing incompatible_core_version")
if strings != translations:
    sys.exit("English translation must match strings.json")
print(
    "OK: SOURCE_COMMIT agrees with README and pinned manifest documentation"
)
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
require_readme "package provenance"
require_readme 'the generated `source_commit` file records the same commit'
require_readme "release status — local/staged integration only"
require_readme "public hacs installation is unavailable"
require_readme "not synchronized"
require_readme "must not be used to validate"
require_readme "local staged integration testing"
require_readme "full home assistant restart"
require_readme "conditional public hacs installation"
require_readme "reviewed public-satellite state (historical evidence)"
require_readme "re-check its current tree before publication"
require_readme "staged tree must match the intended satellite tree"
require_readme "version must uniquely identify that tree"
require_readme "exact home assistant 2025.1.0 plus current-version coverage"
require_readme "official hacs and hassfest"
require_readme "explicit publication authorization"

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
CURRENT_README="${README%%## conditional public hacs installation*}"
if grep -Eqi \
  'https://github\.com/[^[:space:]`]+/zigbeelens-hacs|hacs[[:space:]]*(→|->)[[:space:]]*integrations[[:space:]]*(→|->)[[:space:]]*custom repositories|pre-release install via hacs|hacs is required|requires[^.]{0,120}hacs|(^|[^[:alnum:]_])(install|add|use)([^[:alnum:]_]|$).{0,160}([^[:space:]]*/)?zigbeelens-hacs' \
  <<<"${CURRENT_README}"
then
  fail "README current/local guidance must not direct testing through the public HACS satellite"
else
  ok "README keeps public-HACS installation inside the conditional future section"
fi

if grep -RniE 'password\s*=\s*["\x27][^"\x27]{8,}|api_key\s*=\s*["\x27]|hunter2|secret-pass' "${ROOT}/custom_components" 2>/dev/null; then
  fail "possible secret in custom_components"
else
  ok "no obvious secrets in custom_components"
fi

if [[ "${FAIL}" -ne 0 ]]; then exit 1; fi
echo "HACS repo validation passed."
