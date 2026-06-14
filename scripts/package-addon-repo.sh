#!/usr/bin/env bash
# Stage Home Assistant add-on repository (image-based, GHCR prebuilt).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/addon/zigbeelens"
DIST="${ROOT}/dist/zigbeelens-addons"
OWNER="${GITHUB_OWNER:-theaussiepom}"
IMAGE="ghcr.io/${OWNER}/zigbeelens"

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
4. Open **ZigbeeLens** from the sidebar (Ingress on port 8377)

## Image tags

| Tag | When |
|-----|------|
| \`edge\` / \`main\` | Latest \`main\` branch build |
| \`0.1.0\` | Release tag (matches add-on version) |
| \`latest\` | Latest release |

For pre-release Docker testing, pull \`${IMAGE}:edge\` directly. Add-on version \`0.1.0\` pulls \`:0.1.0\` when that GHCR tag exists.

## Safety

Read-only. No permit join, remove, reset, bind, unbind, OTA, or channel changes.

Documentation: https://github.com/${OWNER}/zigbeelens/blob/main/docs/addon-dev.md
EOF

# Satellite repo CI
mkdir -p "${DIST}/.github/workflows" "${DIST}/scripts"
cp "${ROOT}/release/zigbeelens-addons/.github/workflows/ci.yml" "${DIST}/.github/workflows/ci.yml"
cp "${ROOT}/release/zigbeelens-addons/scripts/validate-addon-repo.sh" "${DIST}/scripts/validate-addon-repo.sh"
chmod +x "${DIST}/scripts/validate-addon-repo.sh"

echo "Packaged add-on repo at ${DIST}"
find "${DIST}" -type f | sort
