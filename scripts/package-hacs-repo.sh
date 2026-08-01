#!/usr/bin/env bash
# Stage HACS install repository (custom_components at repo root).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist/zigbeelens-hacs"
SOURCE_REPOSITORY="${ZIGBEELENS_SOURCE_REPOSITORY-theaussiepom/zigbeelens}"
FUTURE_HACS_REPOSITORY="${ZIGBEELENS_FUTURE_HACS_REPOSITORY-theaussiepom/zigbeelens-hacs}"
PRE_SYNC_HACS_REPOSITORY="theaussiepom/zigbeelens-hacs"

PACKAGE_INPUTS=(
  apps/ha_integration/custom_components/zigbeelens
  apps/ha_integration/docs
  apps/ha_integration/tests
  apps/ha_integration/ha-test-matrix.json
  apps/ha_integration/pytest.ini
  apps/ha_integration/requirements-test.txt
  apps/ha_integration/requirements-test-minimum.txt
  apps/ha_integration/requirements-test-current.txt
  apps/core/tests/fixtures/http_origin_vectors.json
  LICENSE
  CHANGELOG.md
  release/zigbeelens-hacs/README.md.in
  release/zigbeelens-hacs/release-evidence.json
  release/zigbeelens-hacs/.github/workflows
  release/zigbeelens-hacs/scripts/validate-hacs-repo.sh
  scripts/package-hacs-repo.sh
  scripts/test-ha-integration-matrix.sh
)

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

validate_repository_identifier() {
  local variable_name="$1"
  local value="$2"
  local repository="${value#*/}"
  if [[ ! "${value}" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}$ ]] ||
    [[ "${repository}" == "." ]] || [[ "${repository}" == ".." ]]
  then
    fail "${variable_name} must be an exact owner/repository identifier"
  fi
}

if [[ -n "${GITHUB_OWNER+x}" ]]; then
  fail "GITHUB_OWNER is no longer supported; use ZIGBEELENS_SOURCE_REPOSITORY and ZIGBEELENS_FUTURE_HACS_REPOSITORY"
fi
validate_repository_identifier \
  "ZIGBEELENS_SOURCE_REPOSITORY" "${SOURCE_REPOSITORY}"
validate_repository_identifier \
  "ZIGBEELENS_FUTURE_HACS_REPOSITORY" "${FUTURE_HACS_REPOSITORY}"
validate_repository_identifier \
  "pre-synchronization HACS repository" "${PRE_SYNC_HACS_REPOSITORY}"

if ! GIT_TOPLEVEL="$(
  git -C "${ROOT}" rev-parse --show-toplevel 2>/dev/null
)"; then
  fail "package source root must be the exact root of a Git checkout"
fi
if [[ "${GIT_TOPLEVEL}" != "${ROOT}" ]]; then
  fail "package source root must be the exact root of a Git checkout"
fi
if ! HEAD_COMMIT="$(
  git -C "${ROOT}" rev-parse --verify 'HEAD^{commit}' 2>/dev/null
)"; then
  fail "unable to resolve the checked-out Git HEAD commit"
fi

if [[ -n "${ZIGBEELENS_SOURCE_COMMIT+x}" ]]; then
  SOURCE_COMMIT_INPUT="${ZIGBEELENS_SOURCE_COMMIT}"
else
  SOURCE_COMMIT_INPUT="${HEAD_COMMIT}"
fi
SOURCE_COMMIT_VALUE="$(
  printf '%s' "${SOURCE_COMMIT_INPUT}" | tr '[:upper:]' '[:lower:]'
)"
if [[ "${#SOURCE_COMMIT_VALUE}" -ne 40 ]] || [[ "${SOURCE_COMMIT_VALUE}" == *[!0-9a-f]* ]]; then
  fail "ZIGBEELENS_SOURCE_COMMIT must be exactly 40 hexadecimal characters after lowercase normalization"
fi
if ! git -C "${ROOT}" cat-file -e "${SOURCE_COMMIT_VALUE}^{commit}" 2>/dev/null; then
  fail "ZIGBEELENS_SOURCE_COMMIT does not identify an existing commit"
fi
if [[ "${SOURCE_COMMIT_VALUE}" != "${HEAD_COMMIT}" ]]; then
  fail "ZIGBEELENS_SOURCE_COMMIT does not match checked-out HEAD"
fi

if ! git -C "${ROOT}" diff --quiet \
  "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}"
then
  echo "FAIL: tracked package inputs differ from SOURCE_COMMIT:" >&2
  git -C "${ROOT}" diff --name-status \
    "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}" >&2
  exit 1
fi
UNTRACKED_INPUTS="$(
  git -C "${ROOT}" ls-files --others --exclude-standard \
    -- "${PACKAGE_INPUTS[@]}"
)"
if [[ -n "${UNTRACKED_INPUTS}" ]]; then
  echo "FAIL: untracked package inputs are not present in SOURCE_COMMIT:" >&2
  printf '%s\n' "${UNTRACKED_INPUTS}" >&2
  exit 1
fi

SOURCE_SNAPSHOT="$(mktemp -d)"
STAGE_COMPLETE=0
cleanup_source_snapshot() {
  rm -rf "${SOURCE_SNAPSHOT}"
  if [[ "${STAGE_COMPLETE}" -ne 1 ]]; then
    rm -rf "${DIST}"
  fi
}
trap cleanup_source_snapshot EXIT

if ! git -C "${ROOT}" archive \
  --format=tar "${SOURCE_COMMIT_VALUE}" -- "${PACKAGE_INPUTS[@]}" |
  tar -xf - -C "${SOURCE_SNAPSHOT}"
then
  fail "unable to extract package inputs from SOURCE_COMMIT"
fi

SRC="${SOURCE_SNAPSHOT}/apps/ha_integration"
README_IN="${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/README.md.in"
RELEASE_EVIDENCE="${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/release-evidence.json"
VALIDATOR_IN="${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/scripts/validate-hacs-repo.sh"
if [[ ! -f "${README_IN}" ]]; then
  fail "SOURCE_COMMIT is missing release/zigbeelens-hacs/README.md.in"
fi
if [[ ! -f "${RELEASE_EVIDENCE}" ]]; then
  fail "SOURCE_COMMIT is missing release-evidence.json"
fi
if [[ ! -f "${VALIDATOR_IN}" ]]; then
  fail "SOURCE_COMMIT is missing validate-hacs-repo.sh"
fi

rm -rf "${DIST}"
mkdir -p "${DIST}/custom_components" "${DIST}/scripts"
printf '%s\n' "${SOURCE_COMMIT_VALUE}" > "${DIST}/SOURCE_COMMIT"

cp -R "${SRC}/custom_components/zigbeelens" "${DIST}/custom_components/"
cp -R "${SRC}/docs" "${DIST}/docs"
cp -R "${SRC}/tests" "${DIST}/tests"
mkdir -p "${DIST}/tests/fixtures"
cp \
  "${SOURCE_SNAPSHOT}/apps/core/tests/fixtures/http_origin_vectors.json" \
  "${DIST}/tests/fixtures/"
cp "${SRC}/ha-test-matrix.json" "${DIST}/"
cp "${SRC}/pytest.ini" "${DIST}/"
cp "${SRC}/requirements-test.txt" "${DIST}/"
cp "${SRC}/requirements-test-minimum.txt" "${DIST}/"
cp "${SRC}/requirements-test-current.txt" "${DIST}/"
cp "${SOURCE_SNAPSHOT}/LICENSE" "${DIST}/"
cp "${SOURCE_SNAPSHOT}/CHANGELOG.md" "${DIST}/"
cp "${RELEASE_EVIDENCE}" "${DIST}/release-evidence.json"

cat > "${DIST}/hacs.json" <<EOF
{
  "name": "ZigbeeLens",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2025.1.0"
}
EOF

python3 - \
  "${RELEASE_EVIDENCE}" \
  "${SRC}/custom_components/zigbeelens/manifest.json" \
  "${README_IN}" \
  "${VALIDATOR_IN}" \
  "${DIST}/README.md" \
  "${DIST}/scripts/validate-hacs-repo.sh" \
  "${SOURCE_REPOSITORY}" \
  "${FUTURE_HACS_REPOSITORY}" \
  "${SOURCE_COMMIT_VALUE}" \
  "${PRE_SYNC_HACS_REPOSITORY}" <<'PY'
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

VERSION_PATTERN = (
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
)

(
    evidence_path,
    manifest_path,
    readme_template_path,
    validator_template_path,
    readme_output_path,
    validator_output_path,
    source_repository,
    future_hacs_repository,
    source_commit,
    locked_pre_sync_repository,
) = sys.argv[1:]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


try:
    evidence = json.loads(
        Path(evidence_path).read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
    )
except (OSError, json.JSONDecodeError, ValueError) as exc:
    raise SystemExit(f"invalid HACS release evidence: {exc}") from exc

expected_top_level_keys = {
    "pre_sync_satellite",
    "candidate_release_preflight",
}
if not isinstance(evidence, dict) or set(evidence) != expected_top_level_keys:
    raise SystemExit(
        "HACS release evidence must contain exactly: "
        + ", ".join(sorted(expected_top_level_keys))
    )
pre_sync = evidence["pre_sync_satellite"]
candidate_preflight = evidence["candidate_release_preflight"]
expected_pre_sync_keys = {
    "repository",
    "commit",
    "tree",
    "source_commit",
    "manifest_version",
    "reviewed_on",
}
expected_candidate_preflight_keys = {
    "reviewed_on",
    "tag_present",
    "release_present",
}
if not isinstance(pre_sync, dict) or set(pre_sync) != expected_pre_sync_keys:
    raise SystemExit(
        "pre_sync_satellite evidence must contain exactly: "
        + ", ".join(sorted(expected_pre_sync_keys))
    )
if (
    not isinstance(candidate_preflight, dict)
    or set(candidate_preflight) != expected_candidate_preflight_keys
):
    raise SystemExit(
        "candidate_release_preflight evidence must contain exactly: "
        + ", ".join(sorted(expected_candidate_preflight_keys))
    )
if pre_sync["repository"] != locked_pre_sync_repository:
    raise SystemExit(
        "pre-sync HACS evidence repository must remain "
        f"{locked_pre_sync_repository}"
    )
for field in ("commit", "tree", "source_commit"):
    if (
        not isinstance(pre_sync[field], str)
        or re.fullmatch(r"[0-9a-f]{40}", pre_sync[field]) is None
    ):
        raise SystemExit(
            f"pre-sync HACS evidence {field} must be 40 lowercase hex characters"
        )
if (
    not isinstance(pre_sync["manifest_version"], str)
    or re.fullmatch(VERSION_PATTERN, pre_sync["manifest_version"]) is None
):
    raise SystemExit(
        "pre_sync_satellite manifest_version must be canonical semver"
    )
try:
    pre_sync_reviewed_on = date.fromisoformat(pre_sync["reviewed_on"])
except (TypeError, ValueError) as exc:
    raise SystemExit(
        "pre_sync_satellite reviewed_on must be a valid ISO date"
    ) from exc
if pre_sync_reviewed_on.isoformat() != pre_sync["reviewed_on"]:
    raise SystemExit(
        "pre_sync_satellite reviewed_on must be a canonical ISO date"
    )
try:
    candidate_reviewed_on = date.fromisoformat(
        candidate_preflight["reviewed_on"]
    )
except (TypeError, ValueError) as exc:
    raise SystemExit(
        "candidate_release_preflight reviewed_on must be a valid ISO date"
    ) from exc
if candidate_reviewed_on.isoformat() != candidate_preflight["reviewed_on"]:
    raise SystemExit(
        "candidate_release_preflight reviewed_on must be a canonical ISO date"
    )
if candidate_preflight["tag_present"] is not False:
    raise SystemExit("candidate_release_preflight tag_present must be false")
if candidate_preflight["release_present"] is not False:
    raise SystemExit("candidate_release_preflight release_present must be false")

try:
    source_manifest = json.loads(
        Path(manifest_path).read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
    )
except (OSError, json.JSONDecodeError, ValueError) as exc:
    raise SystemExit(f"invalid source integration manifest: {exc}") from exc
candidate_version = (
    source_manifest.get("version") if isinstance(source_manifest, dict) else None
)
if (
    not isinstance(candidate_version, str)
    or re.fullmatch(VERSION_PATTERN, candidate_version) is None
):
    raise SystemExit(
        "candidate source manifest version must be canonical semver"
    )
candidate_release_tag = f"v{candidate_version}"

substitutions = {
    "@SOURCE_REPOSITORY@": source_repository,
    "@FUTURE_HACS_REPOSITORY@": future_hacs_repository,
    "@SOURCE_COMMIT@": source_commit,
    "@PRE_SYNC_HACS_REPOSITORY@": pre_sync["repository"],
    "@PRE_SYNC_HACS_COMMIT@": pre_sync["commit"],
    "@PRE_SYNC_HACS_TREE@": pre_sync["tree"],
    "@PRE_SYNC_HACS_SOURCE_COMMIT@": pre_sync["source_commit"],
    "@PRE_SYNC_HACS_MANIFEST_VERSION@": pre_sync["manifest_version"],
    "@PRE_SYNC_HACS_REVIEW_DATE@": pre_sync["reviewed_on"],
    "@CANDIDATE_VERSION@": candidate_version,
    "@CANDIDATE_RELEASE_TAG@": candidate_release_tag,
    "@CANDIDATE_PREFLIGHT_REVIEW_DATE@": candidate_preflight["reviewed_on"],
    "@CANDIDATE_TAG_STATE@": (
        "present" if candidate_preflight["tag_present"] else "absent"
    ),
    "@CANDIDATE_RELEASE_STATE@": (
        "present" if candidate_preflight["release_present"] else "absent"
    ),
}
placeholder_pattern = re.compile(r"@[A-Z][A-Z0-9_]*@")


def render(template_path, output_path, required_placeholder_counts):
    template = Path(template_path).read_text(encoding="utf-8")
    found_counts = Counter(placeholder_pattern.findall(template))
    unknown = sorted(found_counts.keys() - required_placeholder_counts.keys())
    missing = sorted(required_placeholder_counts.keys() - found_counts.keys())
    if unknown:
        raise SystemExit(
            f"{template_path} contains unknown placeholder(s): "
            + ", ".join(unknown)
        )
    if missing:
        raise SystemExit(
            f"{template_path} is missing required placeholder(s): "
            + ", ".join(missing)
        )
    wrong_counts = sorted(
        (
            placeholder,
            found_counts[placeholder],
            expected_count,
        )
        for placeholder, expected_count in required_placeholder_counts.items()
        if found_counts[placeholder] != expected_count
    )
    if wrong_counts:
        raise SystemExit(
            f"{template_path} contains duplicated or misplaced "
            "placeholder(s): "
            + ", ".join(
                f"{placeholder}={actual} (expected {expected})"
                for placeholder, actual, expected in wrong_counts
            )
        )
    rendered = template
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)
    unresolved = sorted(set(placeholder_pattern.findall(rendered)))
    if unresolved:
        raise SystemExit(
            f"{template_path} contains unresolved placeholder(s): "
            + ", ".join(unresolved)
        )
    Path(output_path).write_text(rendered, encoding="utf-8")


readme_placeholder_counts = {
    "@SOURCE_REPOSITORY@": 6,
    "@FUTURE_HACS_REPOSITORY@": 1,
    "@SOURCE_COMMIT@": 4,
    "@PRE_SYNC_HACS_REPOSITORY@": 2,
    "@PRE_SYNC_HACS_COMMIT@": 1,
    "@PRE_SYNC_HACS_TREE@": 1,
    "@PRE_SYNC_HACS_SOURCE_COMMIT@": 1,
    "@PRE_SYNC_HACS_MANIFEST_VERSION@": 1,
    "@PRE_SYNC_HACS_REVIEW_DATE@": 1,
    "@CANDIDATE_VERSION@": 2,
    "@CANDIDATE_RELEASE_TAG@": 3,
    "@CANDIDATE_PREFLIGHT_REVIEW_DATE@": 1,
    "@CANDIDATE_TAG_STATE@": 1,
    "@CANDIDATE_RELEASE_STATE@": 1,
}
render(
    readme_template_path,
    readme_output_path,
    readme_placeholder_counts,
)
render(
    validator_template_path,
    validator_output_path,
    {
        placeholder: 1
        for placeholder in substitutions
        if placeholder.startswith(("@PRE_SYNC_HACS_", "@CANDIDATE_"))
    },
)
PY

python3 - <<PY
import json
from pathlib import Path

manifest = Path("${DIST}/custom_components/zigbeelens/manifest.json")
data = json.loads(manifest.read_text())
data["documentation"] = "https://github.com/${SOURCE_REPOSITORY}/blob/${SOURCE_COMMIT_VALUE}/docs/hacs.md"
data["issue_tracker"] = "https://github.com/${SOURCE_REPOSITORY}/issues"
manifest.write_text(json.dumps(data, indent=2) + "\n")
PY

mkdir -p "${DIST}/.github/workflows"
cp "${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/.github/workflows/ci.yml" \
  "${DIST}/.github/workflows/ci.yml"
cp "${SOURCE_SNAPSHOT}/release/zigbeelens-hacs/.github/workflows/release.yml" \
  "${DIST}/.github/workflows/release.yml"
cp "${SOURCE_SNAPSHOT}/scripts/test-ha-integration-matrix.sh" \
  "${DIST}/scripts/test-ha-integration-matrix.sh"
chmod +x "${DIST}/scripts/validate-hacs-repo.sh"
chmod +x "${DIST}/scripts/test-ha-integration-matrix.sh"

echo "Packaged HACS repo at ${DIST}"
find "${DIST}" -type f | sort
STAGE_COMPLETE=1
