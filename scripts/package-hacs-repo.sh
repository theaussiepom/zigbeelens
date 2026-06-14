#!/usr/bin/env bash
# Stage HACS install repository (custom_components at repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/ha_integration"
DIST="${ROOT}/dist/zigbeelens-hacs"
OWNER="${GITHUB_OWNER:-theaussiepom}"

rm -rf "${DIST}"
mkdir -p "${DIST}/custom_components"

cp -R "${SRC}/custom_components/zigbeelens" "${DIST}/custom_components/"
find "${DIST}" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
cp "${ROOT}/LICENSE" "${DIST}/"
cp "${ROOT}/CHANGELOG.md" "${DIST}/"

cat > "${DIST}/hacs.json" <<EOF
{
  "name": "ZigbeeLens",
  "content_in_root": true,
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
EOF

cat > "${DIST}/README.md" <<EOF
# ZigbeeLens Home Assistant integration (HACS)

Read-only Home Assistant bridge to [ZigbeeLens Core](https://github.com/${OWNER}/zigbeelens).

## Prerequisites

**ZigbeeLens Core must already be running.** This integration does not collect Zigbee2MQTT data directly.

Run Core using one of:

- **Docker** — \`${OWNER}/zigbeelens\` image from GHCR (see main repo [docs/docker.md](https://github.com/${OWNER}/zigbeelens/blob/main/docs/docker.md))
- **Home Assistant OS add-on** — from [zigbeelens-addons](https://github.com/${OWNER}/zigbeelens-addons) (optional)

## Install via HACS

1. **HACS → Integrations → Custom repositories**
2. Add \`https://github.com/${OWNER}/zigbeelens-hacs\`
3. Category: **Integration**
4. Install **ZigbeeLens** and restart Home Assistant
5. **Settings → Devices & services → Add integration → ZigbeeLens**

## Core URL examples

| Deployment | Typical URL |
|------------|-------------|
| Docker on LAN | \`http://<docker-host-ip>:8377\` |
| Docker Compose service | \`http://zigbeelens:8377\` |
| HAOS add-on | \`http://localhost:8377\` |

## What this integration does

- Summary sensors and binary sensors
- Sidebar panel opening the **Core dashboard**
- Redacted diagnostics and repairs

## What it does not do

- Does **not** mutate Zigbee devices
- Does **not** publish MQTT or Zigbee2MQTT request topics
- Entities are summaries only — Core dashboard remains canonical

## Safety

Read-only bridge to Core.

Issues: https://github.com/${OWNER}/zigbeelens/issues
EOF

python3 - <<PY
import json
from pathlib import Path

manifest = Path("${DIST}/custom_components/zigbeelens/manifest.json")
data = json.loads(manifest.read_text())
data["documentation"] = "https://github.com/${OWNER}/zigbeelens-hacs"
data["issue_tracker"] = "https://github.com/${OWNER}/zigbeelens/issues"
manifest.write_text(json.dumps(data, indent=2) + "\n")
PY

mkdir -p "${DIST}/.github/workflows" "${DIST}/scripts"
cp "${ROOT}/release/zigbeelens-hacs/.github/workflows/ci.yml" "${DIST}/.github/workflows/ci.yml"
cp "${ROOT}/release/zigbeelens-hacs/.github/workflows/release.yml" "${DIST}/.github/workflows/release.yml"
cp "${ROOT}/release/zigbeelens-hacs/scripts/validate-hacs-repo.sh" "${DIST}/scripts/validate-hacs-repo.sh"
chmod +x "${DIST}/scripts/validate-hacs-repo.sh"

echo "Packaged HACS repo at ${DIST}"
find "${DIST}" -type f | sort
