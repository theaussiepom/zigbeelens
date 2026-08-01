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
  release-evidence.json
  LICENSE
  CHANGELOG.md
  .github/workflows/ci.yml
  .github/workflows/release.yml
  ha-test-matrix.json
  pytest.ini
  requirements-test.txt
  requirements-test-minimum.txt
  requirements-test-current.txt
  docs/zigbeelens-icon.svg
  docs/zigbeelens-logo.svg
  scripts/test-ha-integration-matrix.sh
  tests/conftest.py
  tests/fixtures/http_origin_vectors.json
  tests/test_core_origin.py
  tests/test_manifest.py
  tests/test_matrix_contract.py
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
  custom_components/zigbeelens/enrichment_manager.py
  custom_components/zigbeelens/entity.py
  custom_components/zigbeelens/exceptions.py
  custom_components/zigbeelens/ha_enrichment.py
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
if [[ -x "${ROOT}/scripts/test-ha-integration-matrix.sh" ]]; then
  ok "scripts/test-ha-integration-matrix.sh is executable"
else
  fail "scripts/test-ha-integration-matrix.sh must be executable"
fi

python3 - "${ROOT}" "${ROOT}/scripts/validate-hacs-repo.sh" <<'PY'
import json, re, sys
from datetime import date
from pathlib import Path

REPOSITORY_PATTERN = (
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    r"/[A-Za-z0-9_.-]{1,100}"
)
VERSION_PATTERN = (
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
)
PRE_SYNC_HACS_REPOSITORY = "@PRE_SYNC_HACS_REPOSITORY@"
PRE_SYNC_HACS_COMMIT = "@PRE_SYNC_HACS_COMMIT@"
PRE_SYNC_HACS_TREE = "@PRE_SYNC_HACS_TREE@"
PRE_SYNC_HACS_SOURCE_COMMIT = "@PRE_SYNC_HACS_SOURCE_COMMIT@"
PRE_SYNC_HACS_MANIFEST_VERSION = "@PRE_SYNC_HACS_MANIFEST_VERSION@"
PRE_SYNC_HACS_REVIEW_DATE = "@PRE_SYNC_HACS_REVIEW_DATE@"
CANDIDATE_VERSION = "@CANDIDATE_VERSION@"
CANDIDATE_RELEASE_TAG = "@CANDIDATE_RELEASE_TAG@"
CANDIDATE_PREFLIGHT_REVIEW_DATE = "@CANDIDATE_PREFLIGHT_REVIEW_DATE@"
CANDIDATE_TAG_STATE = "@CANDIDATE_TAG_STATE@"
CANDIDATE_RELEASE_STATE = "@CANDIDATE_RELEASE_STATE@"
EXPECTED_HACS_RELEASE_EVIDENCE = {
    "pre_sync_satellite": {
        "repository": PRE_SYNC_HACS_REPOSITORY,
        "commit": PRE_SYNC_HACS_COMMIT,
        "tree": PRE_SYNC_HACS_TREE,
        "source_commit": PRE_SYNC_HACS_SOURCE_COMMIT,
        "manifest_version": PRE_SYNC_HACS_MANIFEST_VERSION,
        "reviewed_on": PRE_SYNC_HACS_REVIEW_DATE,
    },
    "candidate_release_preflight": {
        "reviewed_on": CANDIDATE_PREFLIGHT_REVIEW_DATE,
        "tag_present": CANDIDATE_TAG_STATE == "present",
        "release_present": CANDIDATE_RELEASE_STATE == "present",
    },
}


def repository_is_valid(value: str) -> bool:
    if re.fullmatch(REPOSITORY_PATTERN, value) is None:
        return False
    repository = value.split("/", 1)[1]
    return repository not in {".", ".."}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key!r}")
        result[key] = value
    return result


def load_unique_json(path: Path, label: str):
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"{label} must be valid duplicate-free JSON: {exc}") from exc


root = Path(sys.argv[1])
validator_path = Path(sys.argv[2])
validator_placeholders = sorted(
    set(
        re.findall(
            r"@[A-Z][A-Z0-9_]*@",
            validator_path.read_text(encoding="utf-8"),
        )
    )
)
if validator_placeholders:
    sys.exit(
        "generated validator contains an unresolved template placeholder: "
        + ", ".join(validator_placeholders)
    )
evidence = load_unique_json(
    root / "release-evidence.json",
    "release-evidence.json",
)
if evidence != EXPECTED_HACS_RELEASE_EVIDENCE:
    sys.exit(
        "release-evidence.json does not match the generated exact historical "
        "and candidate-preflight contract"
    )
if PRE_SYNC_HACS_REPOSITORY != "theaussiepom/zigbeelens-hacs":
    sys.exit(
        "pre-synchronization public satellite repository identity is not exact"
    )
if CANDIDATE_RELEASE_TAG != f"v{CANDIDATE_VERSION}":
    sys.exit("candidate release tag does not derive from candidate version")
if CANDIDATE_TAG_STATE != "absent":
    sys.exit("candidate target tag state must be absent")
if CANDIDATE_RELEASE_STATE != "absent":
    sys.exit("candidate target-tag GitHub release state must be absent")
for field in ("commit", "tree", "source_commit"):
    if re.fullmatch(
        r"[0-9a-f]{40}", evidence["pre_sync_satellite"][field]
    ) is None:
        sys.exit(
            "release-evidence.json pre_sync_satellite "
            f"{field} must be 40 lowercase hex characters"
        )
try:
    pre_sync_reviewed_on = date.fromisoformat(PRE_SYNC_HACS_REVIEW_DATE)
except ValueError as exc:
    raise SystemExit(
        "pre-synchronization review date must be a valid ISO date"
    ) from exc
if pre_sync_reviewed_on.isoformat() != PRE_SYNC_HACS_REVIEW_DATE:
    sys.exit("pre-synchronization review date must be canonical")
try:
    candidate_reviewed_on = date.fromisoformat(
        CANDIDATE_PREFLIGHT_REVIEW_DATE
    )
except ValueError as exc:
    raise SystemExit(
        "candidate release preflight review date must be a valid ISO date"
    ) from exc
if candidate_reviewed_on.isoformat() != CANDIDATE_PREFLIGHT_REVIEW_DATE:
    sys.exit("candidate release preflight review date must be canonical")

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
hacs = load_unique_json(root / "hacs.json", "hacs.json")
if hacs.get("content_in_root") is not False:
    sys.exit("hacs.json content_in_root must be false for custom_components layout")
manifest = load_unique_json(
    root / "custom_components/zigbeelens/manifest.json",
    "manifest.json",
)
if manifest.get("domain") != "zigbeelens":
    sys.exit("manifest domain must be zigbeelens")
if not manifest.get("version"):
    sys.exit("manifest version required")
if manifest.get("version") != CANDIDATE_VERSION:
    sys.exit(
        "manifest version does not match generated candidate version"
    )
if manifest.get("config_flow") is not True:
    sys.exit("manifest config_flow must be true")
if manifest.get("single_config_entry") is not True:
    sys.exit("manifest single_config_entry must be true")
if manifest.get("iot_class") != "local_polling":
    sys.exit("manifest iot_class must be local_polling")
if not manifest.get("codeowners"):
    sys.exit("manifest codeowners required")
documentation = manifest.get("documentation")
documentation_match = (
    re.fullmatch(
        r"https://github\.com/"
        r"(?P<repository>"
        + REPOSITORY_PATTERN
        + r")/blob/"
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
source_repository = documentation_match.group("repository")
if not repository_is_valid(source_repository):
    sys.exit(
        "manifest documentation source repository must be an exact "
        "owner/repository identifier"
    )
expected_issue_tracker = f"https://github.com/{source_repository}/issues"
if manifest.get("issue_tracker") != expected_issue_tracker:
    sys.exit(
        "manifest issue tracker does not match the declared source repository"
    )
readme = (root / "README.md").read_text(encoding="utf-8")
unresolved_placeholders = sorted(
    set(re.findall(r"@[A-Z][A-Z0-9_]*@", readme))
)
if unresolved_placeholders:
    sys.exit(
        "README contains an unresolved template placeholder: "
        + ", ".join(unresolved_placeholders)
    )
expected_source_url = f"https://github.com/{source_repository}"
expected_docker_image = f"ghcr.io/{source_repository}"
expected_docker_documentation = (
    f"https://github.com/{source_repository}/blob/"
    f"{source_commit}/docs/docker.md"
)
status_heading = "## Release status — local/staged integration only"
local_heading = "## Local staged integration testing"
future_heading = "## Conditional public HACS installation"
status_start = readme.find(status_heading)
local_start = readme.find(local_heading)
future_start = readme.find(future_heading)
if (
    status_start < 0
    or local_start <= status_start
    or future_start <= local_start
):
    sys.exit(
        "README must contain ordered release-status, local-stage, and "
        "conditional-public-HACS sections"
    )
current_readme = readme[:future_start]
local_readme = readme[local_start:future_start]
future_readme = readme[future_start:]
source_urls = re.findall(
    r"\[ZigbeeLens Core\]\((?P<url>[^)\s]+)\)",
    current_readme,
)
if source_urls != [expected_source_url]:
    sys.exit("README Core repository link does not match source repository")
docker_images = re.findall(
    r"ghcr\.io/[A-Za-z0-9_.-]+/[A-Za-z0-9_.:@/-]+",
    current_readme,
)
if docker_images != [expected_docker_image]:
    sys.exit("README Docker image does not match source repository")
commit_links = re.findall(
    r"\[`(?P<label>[0-9A-Fa-f]{40})`\]\("
    r"https://github\.com/(?P<repository>[^)\s]+?)/commit/"
    r"(?P<commit>[0-9A-Fa-f]{40})\)",
    local_readme,
)
if commit_links != [(source_commit, source_repository, source_commit)]:
    sys.exit("README package source commit does not match SOURCE_COMMIT")
current_documentation_urls = re.findall(
    r"https://github\.com/[^\s)`\]]+/blob/"
    r"[^\s)`\]]+/docs/[^\s)`\]]+",
    current_readme,
)
local_documentation_urls = re.findall(
    r"https://github\.com/[^\s)`\]]+/blob/"
    r"[^\s)`\]]+/docs/[^\s)`\]]+",
    local_readme,
)
if local_documentation_urls.count(documentation) != 1:
    sys.exit(
        "README pinned documentation URL does not match manifest documentation"
    )
if current_documentation_urls.count(expected_docker_documentation) != 1:
    sys.exit(
        "README pinned Docker documentation URL does not match SOURCE_COMMIT/"
        "source repository"
    )
if "/blob/main/docs/" in current_readme:
    sys.exit(
        "README current/local guidance must not use blob/main documentation "
        "(blob/main/docs/)"
    )
expected_current_documentation_urls = sorted(
    (documentation, expected_docker_documentation)
)
if sorted(current_documentation_urls) != expected_current_documentation_urls:
    sys.exit(
        "README current/local operational documentation must use exactly the "
        "declared source repository and SOURCE_COMMIT HACS and Docker URLs"
    )
for current_url in current_documentation_urls:
    repository_and_path = current_url.removeprefix(
        "https://github.com/"
    )
    repository, revision_and_path = repository_and_path.split("/blob/", 1)
    revision, _ = revision_and_path.split("/docs/", 1)
    if (
        not repository_is_valid(repository)
        or repository != source_repository
        or revision != source_commit
    ):
        sys.exit(
            "README current/local operational documentation must use the "
            "declared source repository and SOURCE_COMMIT"
        )
issues_targets = re.findall(
    r"(?i)\bissues:[ \t]*(?P<target>\S+)",
    readme,
)
if issues_targets != [expected_issue_tracker]:
    sys.exit("README issue link does not match manifest/source repository")
future_repository_matches = re.findall(
    r"`https://github\.com/(?P<repository>"
    + REPOSITORY_PATTERN
    + r")` as a HACS Integration",
    future_readme,
)
if (
    len(future_repository_matches) != 1
    or not repository_is_valid(future_repository_matches[0])
):
    sys.exit(
        "README conditional future HACS repository must be one exact "
        "owner/repository URL"
    )
pre_sync_state_pattern = re.compile(
    r"Pre-synchronization satellite historical evidence:\s*"
    r"- repository: `(?P<repository>"
    + REPOSITORY_PATTERN
    + r")`\s*"
    r"- commit: `(?P<commit>[0-9a-f]{40})`\s*"
    r"- tree: `(?P<tree>[0-9a-f]{40})`\s*"
    r"- `SOURCE_COMMIT`: `(?P<source_commit>[0-9a-f]{40})`\s*"
    r"- historical manifest version: `(?P<manifest_version>"
    + VERSION_PATTERN
    + r")`\s*"
    r"- reviewed: `(?P<reviewed_on>[0-9]{4}-[0-9]{2}-[0-9]{2})`",
)
pre_sync_states = list(pre_sync_state_pattern.finditer(readme))
if len(pre_sync_states) != 1:
    sys.exit(
        "README must contain exactly one complete pre-synchronization "
        "historical evidence block"
    )
pre_sync_state = pre_sync_states[0]
pre_sync_repository = pre_sync_state.group("repository")
if not repository_is_valid(pre_sync_repository):
    sys.exit(
        "README pre-synchronization repository is malformed"
    )
readme_evidence = {
    "repository": pre_sync_repository,
    "commit": pre_sync_state.group("commit"),
    "tree": pre_sync_state.group("tree"),
    "source_commit": pre_sync_state.group("source_commit"),
    "manifest_version": pre_sync_state.group("manifest_version"),
    "reviewed_on": pre_sync_state.group("reviewed_on"),
}
if readme_evidence != EXPECTED_HACS_RELEASE_EVIDENCE["pre_sync_satellite"]:
    sys.exit(
        "README pre-synchronization evidence does not match the canonical "
        "generated contract"
    )
try:
    date.fromisoformat(pre_sync_state.group("reviewed_on"))
except ValueError as exc:
    raise SystemExit(
        "README pre-synchronization review date must be a valid ISO date"
    ) from exc
candidate_state_pattern = re.compile(
    r"Candidate release preflight:\s*"
    r"- candidate manifest version: `(?P<manifest_version>"
    + VERSION_PATTERN
    + r")`\s*"
    r"- candidate target tag: `(?P<release_tag>v"
    + VERSION_PATTERN
    + r")`\s*"
    r"- reviewed: `(?P<reviewed_on>[0-9]{4}-[0-9]{2}-[0-9]{2})`\s*"
    r"- target tag state: (?P<tag_state>present|absent)\s*"
    r"- target-tag GitHub release state: "
    r"(?P<release_state>present|absent)",
)
candidate_states = list(candidate_state_pattern.finditer(readme))
if len(candidate_states) != 1:
    sys.exit(
        "README must contain exactly one complete candidate release preflight "
        "block"
    )
candidate_state = candidate_states[0]
candidate_readme_evidence = {
    "manifest_version": candidate_state.group("manifest_version"),
    "release_tag": candidate_state.group("release_tag"),
    "reviewed_on": candidate_state.group("reviewed_on"),
    "tag_present": candidate_state.group("tag_state") == "present",
    "release_present": candidate_state.group("release_state") == "present",
}
expected_candidate_readme_evidence = {
    "manifest_version": CANDIDATE_VERSION,
    "release_tag": CANDIDATE_RELEASE_TAG,
    "reviewed_on": CANDIDATE_PREFLIGHT_REVIEW_DATE,
    "tag_present": CANDIDATE_TAG_STATE == "present",
    "release_present": CANDIDATE_RELEASE_STATE == "present",
}
if candidate_readme_evidence != expected_candidate_readme_evidence:
    sys.exit(
        "README candidate identity does not match the generated manifest and "
        "candidate release preflight"
    )
try:
    date.fromisoformat(candidate_state.group("reviewed_on"))
except ValueError as exc:
    raise SystemExit(
        "README candidate preflight review date must be a valid ISO date"
    ) from exc
if re.search(
    r"re-check\s+the\s+public\s+commit,\s+tree,\s+source\s+provenance,"
    r"\s+tag,\s+and\s+release\s+immediately\s+before\s+any"
    r"\s+synchronization\s+or\s+publication\s+decision",
    readme,
    flags=re.IGNORECASE,
) is None:
    sys.exit(
        "README must require exact public state to be re-checked before action"
    )
strings = json.loads((root / "custom_components/zigbeelens/strings.json").read_text())
translations = json.loads((root / "custom_components/zigbeelens/translations/en.json").read_text())
if "issues" not in strings or "incompatible_core_version" not in strings["issues"]:
    sys.exit("strings.json missing incompatible_core_version")
if "issues" not in translations or "incompatible_core_version" not in translations["issues"]:
    sys.exit("translations/en.json missing incompatible_core_version")
if strings != translations:
    sys.exit("English translation must match strings.json")

expected_matrix = {
    "reviewed_on": "2026-07-23",
    "lanes": [
        {
            "name": "minimum",
            "homeassistant": "2025.1.0",
            "python": "3.12",
            "requirements": "requirements-test-minimum.txt",
        },
        {
            "name": "current",
            "homeassistant": "2026.7.3",
            "python": "3.14",
            "requirements": "requirements-test-current.txt",
        },
    ],
}
matrix = json.loads((root / "ha-test-matrix.json").read_text(encoding="utf-8"))
if matrix != expected_matrix:
    sys.exit("ha-test-matrix.json must contain only the exact reviewed lanes")


def requirement_lines(name: str) -> list[str]:
    return [
        line.strip()
        for line in (root / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


common_requirements = requirement_lines("requirements-test.txt")
if any(
    re.match(r"(?i)^homeassistant(?:$|[\s\[<>=!~;])", line)
    for line in common_requirements
):
    sys.exit(
        "requirements-test.txt must not contain a Home Assistant requirement"
    )
expected_lane_requirements = {
    "requirements-test-minimum.txt": [
        "-r requirements-test.txt",
        "homeassistant==2025.1.0",
    ],
    "requirements-test-current.txt": [
        "-r requirements-test.txt",
        "homeassistant==2026.7.3",
    ],
}
for name, expected_lines in expected_lane_requirements.items():
    if requirement_lines(name) != expected_lines:
        sys.exit(f"{name} must inherit common tests and use its exact HA pin")

ci_workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
release_workflow = (
    root / ".github/workflows/release.yml"
).read_text(encoding="utf-8")
required_ci_fragments = (
    "workflow_call:",
    "bash scripts/validate-hacs-repo.sh",
    'bash scripts/test-ha-integration-matrix.sh "${{ matrix.lane }}"',
    (
        "home-assistant/actions/hassfest@"
        "e3fb68ebda13d88a0d695082f471ba2c83d025fb"
    ),
    "hacs/action@1ebf01c408f29afcb6406bd431bc98fd8cbb15aa",
    "category: integration",
)
for fragment in required_ci_fragments:
    if ci_workflow.count(fragment) != 1:
        sys.exit(
            "generated CI must contain exactly one required validation "
            f"fragment: {fragment}"
        )
expected_ci_lanes = [
    ("minimum", "2025.1.0", "3.12"),
    ("current", "2026.7.3", "3.14"),
]
actual_ci_lanes = re.findall(
    r"(?m)^\s+- lane:\s*(\S+)\s*\n"
    r"\s+homeassistant:\s*[\"']([^\"']+)[\"']\s*\n"
    r"\s+python:\s*[\"']([^\"']+)[\"']\s*$",
    ci_workflow,
)
if actual_ci_lanes != expected_ci_lanes:
    sys.exit("generated CI Home Assistant/Python matrix is not exact")
for action in (
    "home-assistant/actions/hassfest@",
    "hacs/action@",
):
    references = re.findall(re.escape(action) + r"([^\s]+)", ci_workflow)
    if len(references) != 1 or re.fullmatch(
        r"[0-9a-f]{40}", references[0]
    ) is None:
        sys.exit(f"{action} must use exactly one immutable commit reference")


def workflow_job(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:[ \t]*\n"
        r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
        workflow,
    )
    if match is None:
        raise SystemExit(f"generated CI is missing the {name} job")
    return match.group("body")


hassfest_job = workflow_job(ci_workflow, "hassfest")
if (
    hassfest_job.count("uses: actions/checkout@v4") != 1
    or (
        "uses: home-assistant/actions/hassfest@"
        "e3fb68ebda13d88a0d695082f471ba2c83d025fb"
    )
    not in hassfest_job
):
    sys.exit("hassfest job must validate the checked-out repository tree")
hacs_job = workflow_job(ci_workflow, "hacs")
if (
    re.search(r"(?m)^\s{4}permissions:\s*\{\}\s*$", hacs_job) is None
    or (
        "uses: hacs/action@"
        "1ebf01c408f29afcb6406bd431bc98fd8cbb15aa"
    )
    not in hacs_job
    or re.search(r"(?m)^\s{10}category:\s*integration\s*$", hacs_job)
    is None
):
    sys.exit("HACS job must use the official no-permissions validation contract")

validation_job = re.search(
    r"(?ms)^  validation:[ \t]*\n"
    r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
    release_workflow,
)
if (
    release_workflow.count("uses: ./.github/workflows/ci.yml") != 1
    or validation_job is None
    or re.search(
        r"(?m)^\s{4}uses:\s*\./\.github/workflows/ci\.yml\s*$",
        validation_job.group("body"),
    )
    is None
):
    sys.exit(
        "generated release validation job must call the local CI workflow"
    )
release_job = re.search(
    r"(?ms)^  release:[ \t]*\n"
    r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
    release_workflow,
)
if release_job is None or re.search(
    r"(?m)^\s{4}needs:\s*validation\s*$",
    release_job.group("body"),
) is None:
    sys.exit("generated release publish job must depend on validation")
print(
    "OK: SOURCE_COMMIT agrees with README and pinned manifest documentation"
)
print("OK: source, future, and reviewed repository identities are separated")
print("OK: exact Home Assistant matrix and requirement pins are sealed")
print("OK: generated CI and release validation semantics are sealed")
print(
    "OK: hacs.json, manifest.json, strings.json, translations/en.json parse"
)
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

README="$(
  tr '[:upper:]' '[:lower:]' < "${ROOT}/README.md" |
    tr '\n' ' ' |
    sed -E 's/[[:space:]]+/ /g'
)"
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
require_readme "public hacs installation remains unavailable"
require_readme "pre-release candidate, not a public release"
require_readme "synchronization alone does not authorize installation or release"
require_readme "its presence does not imply that a public release has been authorized"
require_readme "local staged integration testing"
require_readme "full home assistant restart"
require_readme "conditional public hacs installation"
require_readme "pre-synchronization satellite historical evidence"
require_readme "historical manifest version"
require_readme "candidate release preflight"
require_readme "candidate manifest version"
require_readme "candidate target tag"
require_readme "not a claim about the satellite state after synchronization"
require_readme '`source_commit` plus the generated git tree identify this candidate'
require_readme "does not distinguish pre-release candidate trees by itself"
require_readme "tag and github release"
require_readme "exact generated tree is the reviewed satellite tree"
require_readme '| minimum | `2025.1.0` | `3.12` |'
require_readme '| current | `2026.7.3` | `3.14` |'
require_readme "official hacs and hassfest"
require_readme "final release authorization is recorded"

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
if grep -Eqi \
  '050d118b3e1406343255594fe64cd569e2420888|previously unused version|unused version|unsynchroni[sz]ed[^.]{0,120}(satellite|stage|candidate|tree)|(satellite|stage|candidate|tree)[^.]{0,120}unsynchroni[sz]ed|(satellite|stage|candidate|tree)[^.]{0,120}(not|never)[^.]{0,80}synchroni[sz]|(not|never)[^.]{0,80}synchroni[sz][^.]{0,120}(satellite|stage|candidate|tree)|(manifest |package )?version[^.]{0,160}(unique|identif)|(candidate|tree)[^.]{0,160}(unique|identif)[^.]{0,80}(manifest |package )?version' \
  <<<"${README}"
then
  fail "README contains stale pre-release synchronization or version-only identity"
else
  ok "README omits stale synchronization and version-only identity claims"
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
