#!/usr/bin/env bash
# Open a PR to home-assistant/brands with ZigbeeLens CDN icons for the HACS UI.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/apps/ha_integration/custom_components/zigbeelens/brand"
WORK="${ROOT}/.tmp/home-assistant-brands"
OWNER="${GITHUB_OWNER:-theaussiepom}"
UPSTREAM="home-assistant/brands"
BRANCH="add-zigbeelens-brand-icons"

for f in icon.png icon@2x.png logo.png logo@2x.png; do
  if [[ ! -f "${SRC}/${f}" ]]; then
    echo "Missing ${SRC}/${f}. Run: python3 scripts/generate-ha-brand-icons.py" >&2
    exit 1
  fi
done

rm -rf "${WORK}"
git clone --depth 1 "https://github.com/${OWNER}/brands.git" "${WORK}" 2>/dev/null \
  || git clone --depth 1 "https://github.com/${UPSTREAM}.git" "${WORK}"

cd "${WORK}"
git remote add upstream "https://github.com/${UPSTREAM}.git" 2>/dev/null || true
git fetch upstream master
git checkout -B "${BRANCH}" upstream/master

DEST="custom_integrations/zigbeelens"
mkdir -p "${DEST}"
cp "${SRC}/icon.png" "${SRC}/icon@2x.png" "${SRC}/logo.png" "${SRC}/logo@2x.png" "${DEST}/"

git add "${DEST}"
if git diff --cached --quiet; then
  echo "No brand changes to publish."
  exit 0
fi

git commit -m "$(cat <<'EOF'
Add ZigbeeLens custom integration brand icons

HACS resolves integration icons from brands.home-assistant.io; inline
custom_components/zigbeelens/brand/ covers HA Settings but not the HACS UI.
EOF
)"

git push -u origin "${BRANCH}" --force

gh pr create \
  --repo "${UPSTREAM}" \
  --head "${OWNER}:${BRANCH}" \
  --title "Add ZigbeeLens custom integration brand icons" \
  --body "$(cat <<EOF
## Summary
- Add \`custom_integrations/zigbeelens/\` icon and logo assets for the ZigbeeLens HACS integration (\`theaussiepom/zigbeelens-hacs\`).
- HA Settings already serves inline brand assets from the integration package; this PR fixes the missing icon in the **HACS downloads UI**, which still uses the brands CDN (same pattern as Scrypted).

## Test plan
- [ ] \`https://brands.home-assistant.io/_/zigbeelens/icon.png\` serves the new icon after deploy
- [ ] HACS → Downloads shows the ZigbeeLens icon for the custom repository
EOF
)" || echo "PR may already exist — check https://github.com/${UPSTREAM}/pulls"

echo "Done. Track PR at https://github.com/${UPSTREAM}/pulls"
