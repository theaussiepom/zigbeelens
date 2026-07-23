#!/usr/bin/env bash
# Validate add-on repository layout (run from repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ADDON="${ROOT}/zigbeelens"
FAIL=0

fail() { echo "FAIL: $1" >&2; FAIL=1; }
ok() { echo "OK: $1"; }

echo "=== ZigbeeLens add-on repo validation ==="

for f in repository.yaml zigbeelens/config.yaml zigbeelens/README.md zigbeelens/icon.png zigbeelens/logo.png zigbeelens/translations/en.yaml; do
  if [[ -f "${ROOT}/${f}" ]]; then ok "$f"; else fail "missing $f"; fi
done

grep -q 'ingress_port: 8377' "${ADDON}/config.yaml" && ok "ingress_port 8377" || fail "ingress_port must be 8377"

grep -q '^image: ghcr.io/' "${ADDON}/config.yaml" && ok "GHCR image configured" || fail "image must point to ghcr.io"

grep -q 'password: ""' "${ADDON}/config.yaml" && ok "no embedded default secrets" || fail "check default password field"

grep -q 'mqtt_discovery: false' "${ADDON}/config.yaml" && ok "mqtt_discovery disabled by default" || fail "mqtt_discovery should default false"

TOPOLOGY_DEFAULTS="$(
  awk '
    /^  topology:$/ && !found { found = 1; next }
    found && /^  [^ ]/ { exit }
    found { print }
  ' "${ADDON}/config.yaml"
)"
if grep -qx '    enabled: true' <<<"${TOPOLOGY_DEFAULTS}" \
  && grep -qx '    startup_scan: true' <<<"${TOPOLOGY_DEFAULTS}"; then
  ok "topology enabled with startup scan by default"
else
  fail "topology defaults must set enabled and startup_scan true"
fi

README="$(tr '[:upper:]' '[:lower:]' < "${ADDON}/README.md")"
for required in \
  "generated repository publication blocked" \
  "not a supported release install" \
  "conditional install after publication" \
  "source-built runner"
do
  if grep -Fq "${required}" <<<"${README}"; then
    ok "README mentions: ${required}"
  else
    fail "README missing publication-status concept: ${required}"
  fi
done

if [[ "${FAIL}" -ne 0 ]]; then exit 1; fi
echo "Add-on repo validation passed."
