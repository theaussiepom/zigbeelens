#!/usr/bin/env bash
# Stage Home Assistant add-on repository (image-based, GHCR prebuilt).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/addon/zigbeelens"
DIST="${ROOT}/dist/zigbeelens-addons"
OWNER="${GITHUB_OWNER:-theaussiepom}"
IMAGE="ghcr.io/${OWNER}/zigbeelens"
ADDON_VERSION="$(
  sed -nE 's/^version: "?([^"]+)"?/\1/p' "${SRC}/config.yaml" | head -1
)"
if [[ -z "${ADDON_VERSION}" ]]; then
  echo "FAIL: add-on version not found in ${SRC}/config.yaml" >&2
  exit 1
fi

rm -rf "${DIST}"
mkdir -p "${DIST}/zigbeelens/translations"

cp "${SRC}/icon.png" "${SRC}/logo.png" "${DIST}/zigbeelens/"
cp "${SRC}/CHANGELOG.md" "${DIST}/zigbeelens/"
cp "${SRC}/translations/en.yaml" "${DIST}/zigbeelens/translations/"
cp "${SRC}/config.yaml" "${DIST}/zigbeelens/config.yaml"

# Image-based add-on — no Dockerfile in release repo (uses GHCR multi-arch image).
if grep -q '^url:' "${DIST}/zigbeelens/config.yaml"; then
  sed -i.bak "s|^url:.*|url: https://github.com/${OWNER}/zigbeelens-addons|" "${DIST}/zigbeelens/config.yaml"
else
  echo "url: https://github.com/${OWNER}/zigbeelens-addons" >> "${DIST}/zigbeelens/config.yaml"
fi
rm -f "${DIST}/zigbeelens/config.yaml.bak"

if grep -q '^image:' "${DIST}/zigbeelens/config.yaml"; then
  sed -i.bak "s|^image:.*|image: ${IMAGE}|" "${DIST}/zigbeelens/config.yaml"
else
  sed -i.bak "/^slug:/a\\
image: ${IMAGE}
" "${DIST}/zigbeelens/config.yaml"
fi
rm -f "${DIST}/zigbeelens/config.yaml.bak"

cat > "${DIST}/repository.yaml" <<EOF
name: ZigbeeLens Add-ons
url: https://github.com/${OWNER}/zigbeelens-addons
maintainer: ZigbeeLens contributors
EOF

cat > "${DIST}/zigbeelens/README.md" <<EOF
# ZigbeeLens Home Assistant add-on

Read-only observability and diagnostics for Zigbee2MQTT networks.

Uses the published container image: \`${IMAGE}\`

## Install

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**
2. Add: \`https://github.com/${OWNER}/zigbeelens-addons\`
3. Install **ZigbeeLens**, configure MQTT and networks, start the add-on
4. Open **ZigbeeLens** from the sidebar (Supervisor Ingress; no host port is published)

## Image tags

| Tag | When |
|-----|------|
| \`edge\` / \`main\` | Latest \`main\` branch build |
| \`${ADDON_VERSION}\` | Release tag (matches add-on version) |
| \`latest\` | Latest release |

For pre-release Docker testing, pull \`${IMAGE}:edge\` directly. Add-on version \`${ADDON_VERSION}\` pulls \`:${ADDON_VERSION}\` when that GHCR tag exists.

## Current package limitations

- Publication is blocked until the packaged HAOS artifact proves UID-1000
  \`/data\` writability, Supervisor Ingress access, and rejection of spoofed
  Ingress identity.
- The image-based package does not currently propagate the optional add-on API
  token into Core. Leave that option empty and use the admin-only Ingress UI.
- Supervisor Ingress is the supported dashboard route. This package publishes
  no portable Core origin for the optional HACS companion integration.
- The three \`reporting.max_*\` options must be at least \`1\`; although the
  current Supervisor schema accepts \`0\`, Core rejects it during startup.

## Safety

Read-only for Zigbee device control: no permit join, remove, reset, bind,
unbind, OTA, channel changes, or device \`/set\` commands. The default add-on
policy may publish one exact allowlisted
\`{base_topic}/bridge/request/networkmap\` diagnostic request after startup;
periodic/manual/incident capture is off, and MQTT Discovery is off.

Documentation: https://github.com/${OWNER}/zigbeelens/blob/main/apps/addon/zigbeelens/README.md
EOF

# Satellite repo CI
mkdir -p "${DIST}/.github/workflows" "${DIST}/scripts"
cp "${ROOT}/release/zigbeelens-addons/.github/workflows/ci.yml" "${DIST}/.github/workflows/ci.yml"
cp "${ROOT}/release/zigbeelens-addons/scripts/validate-addon-repo.sh" "${DIST}/scripts/validate-addon-repo.sh"
chmod +x "${DIST}/scripts/validate-addon-repo.sh"

echo "Packaged add-on repo at ${DIST}"
find "${DIST}" -type f | sort
