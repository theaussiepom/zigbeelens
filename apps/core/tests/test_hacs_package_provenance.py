"""Regression tests for staged HACS package source provenance."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGER = ROOT / "scripts" / "package-hacs-repo.sh"
README_TEMPLATE = ROOT / "release" / "zigbeelens-hacs" / "README.md.in"
PRE_SYNC_EVIDENCE_SOURCE = (
    ROOT / "release" / "zigbeelens-hacs" / "pre-sync-evidence.json"
)
PACKAGE_VALIDATOR = (
    ROOT / "release" / "zigbeelens-hacs" / "scripts" / "validate-hacs-repo.sh"
)
INTEGRATION_SOURCE = (
    ROOT / "apps" / "ha_integration" / "custom_components" / "zigbeelens"
)
INTEGRATION_ROOT = ROOT / "apps" / "ha_integration"
INTEGRATION_TESTS = INTEGRATION_ROOT / "tests"
MATRIX_RUNNER = ROOT / "scripts" / "test-ha-integration-matrix.sh"
HA_VALIDATOR = ROOT / "scripts" / "validate-ha-integration.sh"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release-check.yml"
WORKFLOW_SOURCE = (
    ROOT / "release" / "zigbeelens-hacs" / ".github" / "workflows"
)

HA_MATRIX_JOB_NAME = "ha-integration-matrix"
HACS_PACKAGE_COMMAND = "bash scripts/package-hacs-repo.sh"
HACS_VALIDATE_COMMAND = (
    "bash dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh"
)
STAGED_HA_MATRIX_COMMAND = (
    "bash dist/zigbeelens-hacs/scripts/test-ha-integration-matrix.sh "
    '"${{ matrix.lane }}"'
)
SOURCE_HA_MATRIX_COMMAND = (
    'bash scripts/test-ha-integration-matrix.sh "${{ matrix.lane }}"'
)
LOCAL_HACS_PACKAGE_COMMAND = 'bash "${ROOT}/scripts/package-hacs-repo.sh"'
LOCAL_HACS_VALIDATE_COMMAND = (
    'bash "${ROOT}/dist/zigbeelens-hacs/scripts/validate-hacs-repo.sh"'
)
LOCAL_STAGED_HA_MATRIX_COMMAND = (
    'bash "${ROOT}/dist/zigbeelens-hacs/scripts/'
    'test-ha-integration-matrix.sh"'
)
LOCAL_SOURCE_HA_MATRIX_COMMAND = (
    'bash "${ROOT}/scripts/test-ha-integration-matrix.sh"'
)

DEFAULT_SOURCE_REPOSITORY = "theaussiepom/zigbeelens"
DEFAULT_FUTURE_HACS_REPOSITORY = "theaussiepom/zigbeelens-hacs"
EXPECTED_PRE_SYNC_EVIDENCE = {
    "repository": "theaussiepom/zigbeelens-hacs",
    "commit": "21c24e3355369b94c9ab596cf9fc0591f1282297",
    "tree": "9e33bcbf919cdc90eee37e6c3f635f6b6292fbc9",
    "source_commit": "906527063ad8bd594fbec51f69f6fc72205302dd",
    "manifest_version": "0.1.14",
    "reviewed_on": "2026-07-29",
    "release_tag": "v0.1.14",
    "tag_present": False,
    "release_present": False,
}
HASSFEST_COMMIT = "e3fb68ebda13d88a0d695082f471ba2c83d025fb"
HACS_ACTION_COMMIT = "1ebf01c408f29afcb6406bd431bc98fd8cbb15aa"
EXPECTED_HA_MATRIX = {
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


def _pre_sync_placeholders(
    evidence: dict[str, object] = EXPECTED_PRE_SYNC_EVIDENCE,
) -> dict[str, str]:
    return {
        "@PRE_SYNC_HACS_REPOSITORY@": str(evidence["repository"]),
        "@PRE_SYNC_HACS_COMMIT@": str(evidence["commit"]),
        "@PRE_SYNC_HACS_TREE@": str(evidence["tree"]),
        "@PRE_SYNC_HACS_SOURCE_COMMIT@": str(evidence["source_commit"]),
        "@PRE_SYNC_HACS_VERSION@": str(evidence["manifest_version"]),
        "@PRE_SYNC_HACS_REVIEW_DATE@": str(evidence["reviewed_on"]),
        "@PRE_SYNC_HACS_RELEASE_TAG@": str(evidence["release_tag"]),
        "@PRE_SYNC_HACS_TAG_STATE@": (
            "present" if evidence["tag_present"] else "absent"
        ),
        "@PRE_SYNC_HACS_RELEASE_STATE@": (
            "present" if evidence["release_present"] else "absent"
        ),
    }


def _render_template(text: str, substitutions: dict[str, str]) -> str:
    rendered = text
    for placeholder, value in substitutions.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def _expected_pre_sync_readme_block() -> str:
    evidence = EXPECTED_PRE_SYNC_EVIDENCE
    return (
        "Pre-synchronization historical evidence:\n\n"
        f"- repository: `{evidence['repository']}`\n"
        f"- commit: `{evidence['commit']}`\n"
        f"- tree: `{evidence['tree']}`\n"
        f"- `SOURCE_COMMIT`: `{evidence['source_commit']}`\n"
        f"- manifest version: `{evidence['manifest_version']}`\n"
        f"- reviewed: `{evidence['reviewed_on']}`\n"
        f"- `{evidence['release_tag']}` tag: absent\n"
        f"- `{evidence['release_tag']}` release: absent"
    )


def _job_body(workflow: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:[ \t]*\n"
        rf"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*\n|\Z)",
        workflow,
    )
    assert match is not None, f"missing workflow job: {job_name}"
    return match.group("body")


def _single_line_run_commands(body: str) -> list[str]:
    return [
        match.group("command").strip()
        for match in re.finditer(
            r"(?m)^[ \t]+run:[ \t]*(?P<command>[^\n]+)$",
            body,
        )
    ]


def _exact_run_position(body: str, command: str) -> int:
    matches = list(
        re.finditer(
            rf"(?m)^[ \t]+run:[ \t]*{re.escape(command)}[ \t]*$",
            body,
        )
    )
    assert len(matches) == 1, f"expected exactly one workflow run: {command}"
    return matches[0].start()


def _shell_invocations(script: str, basename: str) -> list[str]:
    return [
        match.group(0).strip()
        for match in re.finditer(
            rf"(?m)^[ \t]*bash[^\n]*{re.escape(basename)}[^\n]*$",
            script,
        )
    ]


def _exact_shell_position(script: str, command: str) -> int:
    matches = list(
        re.finditer(
            rf"(?m)^[ \t]*{re.escape(command)}[ \t]*$",
            script,
        )
    )
    assert len(matches) == 1, f"expected exactly one shell command: {command}"
    return matches[0].start()


def _assert_ha_matrix_job_contract(workflow: str) -> None:
    assert re.search(r"(?m)^defaults:\s*$", workflow) is None
    workflow_lowered = workflow.lower()
    for forbidden in (
        "theaussiepom/zigbeelens-hacs",
        "zigbeelens_source_repository",
        "zigbeelens_source_commit",
    ):
        assert forbidden not in workflow_lowered

    body = _job_body(workflow, HA_MATRIX_JOB_NAME)
    assert re.search(r"(?m)^    timeout-minutes:\s*30\s*$", body)
    assert re.findall(
        r"(?m)^\s+- lane:\s*(\S+)\s*\n"
        r"\s+homeassistant:\s*[\"']([^\"']+)[\"']\s*\n"
        r"\s+python:\s*[\"']([^\"']+)[\"']\s*$",
        body,
    ) == [
        ("minimum", "2025.1.0", "3.12"),
        ("current", "2026.7.3", "3.14"),
    ]

    commands = _single_line_run_commands(body)
    assert commands == [
        HACS_PACKAGE_COMMAND,
        HACS_VALIDATE_COMMAND,
        STAGED_HA_MATRIX_COMMAND,
    ]
    assert [
        command
        for command in commands
        if "package-hacs-repo.sh" in command
    ] == [HACS_PACKAGE_COMMAND]
    assert [
        command
        for command in commands
        if "validate-hacs-repo.sh" in command
    ] == [HACS_VALIDATE_COMMAND]
    assert [
        command
        for command in commands
        if "test-ha-integration-matrix.sh" in command
    ] == [STAGED_HA_MATRIX_COMMAND]
    assert SOURCE_HA_MATRIX_COMMAND not in body

    package = _exact_run_position(body, HACS_PACKAGE_COMMAND)
    validate = _exact_run_position(body, HACS_VALIDATE_COMMAND)
    matrix = _exact_run_position(body, STAGED_HA_MATRIX_COMMAND)
    assert package < validate < matrix
    assert "dist/zigbeelens-hacs" not in body[:package]

    for setup in (
        "uses: actions/setup-python@v5",
        "uses: actions/setup-node@v4",
    ):
        assert body.count(setup) == 1
        assert body.index(setup) < package
    assert body.count("uses: actions/checkout@v4") == 1
    assert body.count("python-version: ${{ matrix.python }}") == 1
    assert body.count("node-version: 22") == 1
    assert body.count("ZIGBEELENS_HA_TEST_PYTHON: python") == 1

    lowered = body.lower()
    for forbidden in (
        "continue-on-error:",
        "--skip-matrix",
        "|| true",
        "if: false",
        "if: ${{ false }}",
        "run: true",
        "run: echo",
        "artifact",
        "git clone",
        "gh repo clone",
        "apps/ha_integration/custom_components",
    ):
        assert forbidden not in lowered, (
            f"Home Assistant matrix job contains weakening: {forbidden}"
        )
    assert re.search(
        r"(?m)^\s+(?:defaults|exclude|if|needs|repository|ref|shell):\s*",
        body,
    ) is None
    assert re.search(
        r"(?i)https?://github\.com/[^\s\"']*/zigbeelens-hacs",
        body,
    ) is None


def _assert_canonical_ha_validator_contract(script: str) -> None:
    assert script.count("set -euo pipefail") == 1
    assert re.findall(
        r"(?m)^[ \t]*set[ \t]+[^\n]+$",
        script,
    ) == ["set -euo pipefail"]
    assert _shell_invocations(script, "package-hacs-repo.sh") == [
        LOCAL_HACS_PACKAGE_COMMAND
    ]
    assert _shell_invocations(script, "validate-hacs-repo.sh") == [
        LOCAL_HACS_VALIDATE_COMMAND
    ]
    assert _shell_invocations(script, "test-ha-integration-matrix.sh") == [
        LOCAL_STAGED_HA_MATRIX_COMMAND
    ]
    assert re.search(
        rf"(?m)^[ \t]*{re.escape(LOCAL_SOURCE_HA_MATRIX_COMMAND)}[ \t]*$",
        script,
    ) is None

    package = _exact_shell_position(script, LOCAL_HACS_PACKAGE_COMMAND)
    validate = _exact_shell_position(script, LOCAL_HACS_VALIDATE_COMMAND)
    matrix = _exact_shell_position(script, LOCAL_STAGED_HA_MATRIX_COMMAND)
    assert package < validate < matrix
    assert "dist/zigbeelens-hacs" not in script[:package]

    assert script.count(
        'if [[ "${1:-}" == "--skip-matrix" ]]; then'
    ) == 1
    assert script.count("SKIP_MATRIX=1") == 1
    assert script.count('if [[ "${SKIP_MATRIX}" -eq 0 ]]; then') == 1
    matrix_gate = re.search(
        r'(?ms)^if \[\[ "\${SKIP_MATRIX}" -eq 0 \]\]; then[ \t]*\n'
        r"(?P<execute>.*?)^else[ \t]*\n"
        r"(?P<skip>.*?)^fi[ \t]*$",
        script,
    )
    assert matrix_gate is not None
    assert package < validate < matrix_gate.start() < matrix
    assert LOCAL_STAGED_HA_MATRIX_COMMAND in matrix_gate.group("execute")
    assert LOCAL_STAGED_HA_MATRIX_COMMAND not in matrix_gate.group("skip")
    assert (
        "Exact Home Assistant integration matrix is owned by separate CI jobs"
        in matrix_gate.group("skip")
    )

    lowered = script.lower()
    for forbidden in (
        "|| true",
        "git clone",
        "gh repo clone",
        "theaussiepom/zigbeelens-hacs",
        "zigbeelens_source_repository",
        "zigbeelens_source_commit",
    ):
        assert forbidden not in lowered, (
            f"canonical Home Assistant validator contains weakening: {forbidden}"
        )
    assert re.search(
        r"(?i)https?://github\.com/[^\s\"']*/zigbeelens-hacs",
        script,
    ) is None


def _assert_downstream_matrix_dependencies(
    ci_workflow: str,
    release_workflow: str,
) -> None:
    packaging = _job_body(ci_workflow, "packaging")
    assert re.search(
        r"(?ms)^    needs:\s*\[[^\]]*\bha-integration-matrix\b[^\]]*\]",
        packaging,
    )
    release_gate = _job_body(release_workflow, "release-gate")
    assert re.search(
        r"(?m)^    needs:\s*\[[^\]]*\bha-integration-matrix\b"
        r"[^\]]*\benrichment-live-e2e\b[^\]]*\]\s*$",
        release_gate,
    )


def _mutate_ha_matrix_job(workflow: str, old: str, new: str) -> str:
    body = _job_body(workflow, HA_MATRIX_JOB_NAME)
    assert old in body
    weakened = body.replace(old, new, 1)
    assert weakened != body
    return workflow.replace(body, weakened, 1)


def _swap_once(text: str, first: str, second: str) -> str:
    assert text.count(first) == 1
    assert text.count(second) == 1
    sentinel = "__ZIGBEELENS_CONTRACT_SWAP__"
    assert sentinel not in text
    return (
        text.replace(first, sentinel, 1)
        .replace(second, first, 1)
        .replace(sentinel, second, 1)
    )


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _copy_fixture_files(repository: Path) -> None:
    _copy_file(PACKAGER, repository / "scripts" / "package-hacs-repo.sh")
    _copy_file(
        MATRIX_RUNNER,
        repository / "scripts" / "test-ha-integration-matrix.sh",
    )
    _copy_file(
        README_TEMPLATE,
        repository / "release" / "zigbeelens-hacs" / "README.md.in",
    )
    _copy_file(
        PRE_SYNC_EVIDENCE_SOURCE,
        repository
        / "release"
        / "zigbeelens-hacs"
        / "pre-sync-evidence.json",
    )
    _copy_file(
        PACKAGE_VALIDATOR,
        repository
        / "release"
        / "zigbeelens-hacs"
        / "scripts"
        / "validate-hacs-repo.sh",
    )
    for workflow in ("ci.yml", "release.yml"):
        _copy_file(
            WORKFLOW_SOURCE / workflow,
            repository
            / "release"
            / "zigbeelens-hacs"
            / ".github"
            / "workflows"
            / workflow,
        )
    _copy_file(ROOT / "LICENSE", repository / "LICENSE")
    _copy_file(ROOT / "CHANGELOG.md", repository / "CHANGELOG.md")
    _copy_file(ROOT / ".gitignore", repository / ".gitignore")
    for name in (
        "ha-test-matrix.json",
        "pytest.ini",
        "requirements-test.txt",
        "requirements-test-minimum.txt",
        "requirements-test-current.txt",
    ):
        _copy_file(
            INTEGRATION_ROOT / name,
            repository / "apps" / "ha_integration" / name,
        )
    for name in ("zigbeelens-icon.svg", "zigbeelens-logo.svg"):
        _copy_file(
            INTEGRATION_ROOT / "docs" / name,
            repository / "apps" / "ha_integration" / "docs" / name,
        )
    _copy_file(
        ROOT / "apps" / "core" / "tests" / "fixtures"
        / "http_origin_vectors.json",
        repository / "apps" / "core" / "tests" / "fixtures"
        / "http_origin_vectors.json",
    )
    shutil.copytree(
        INTEGRATION_SOURCE,
        repository
        / "apps"
        / "ha_integration"
        / "custom_components"
        / "zigbeelens",
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".DS_Store",
        ),
    )
    shutil.copytree(
        INTEGRATION_TESTS,
        repository / "apps" / "ha_integration" / "tests",
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".pytest_cache",
            ".DS_Store",
        ),
    )


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
    )


def _git_text(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_bytes(repository: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
    ).stdout


def _commit_all(repository: Path, message: str) -> None:
    _run_git(repository, "add", ".")
    _run_git(repository, "commit", "-qm", message)


def _fixture_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    _copy_fixture_files(repository)

    _run_git(repository, "init", "-q")
    _run_git(repository, "config", "user.name", "ZigbeeLens Tests")
    _run_git(repository, "config", "user.email", "tests@zigbeelens.invalid")
    _commit_all(repository, "fixture")
    return repository


def _head(repository: Path) -> str:
    return _git_text(repository, "rev-parse", "HEAD")


def _run_packager(
    repository: Path,
    *,
    source_commit: str | None = None,
    source_repository: str | None = None,
    future_hacs_repository: str | None = None,
    legacy_github_owner: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for variable in (
        "ZIGBEELENS_SOURCE_COMMIT",
        "ZIGBEELENS_SOURCE_REPOSITORY",
        "ZIGBEELENS_FUTURE_HACS_REPOSITORY",
        "GITHUB_OWNER",
    ):
        env.pop(variable, None)
    if source_commit is not None:
        env["ZIGBEELENS_SOURCE_COMMIT"] = source_commit
    if source_repository is not None:
        env["ZIGBEELENS_SOURCE_REPOSITORY"] = source_repository
    if future_hacs_repository is not None:
        env["ZIGBEELENS_FUTURE_HACS_REPOSITORY"] = future_hacs_repository
    if legacy_github_owner is not None:
        env["GITHUB_OWNER"] = legacy_github_owner
    return subprocess.run(
        ["bash", "scripts/package-hacs-repo.sh"],
        cwd=repository,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_package_validator(repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/validate-hacs-repo.sh"],
        cwd=repository / "dist" / "zigbeelens-hacs",
        check=False,
        capture_output=True,
        text=True,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"


def _assert_packager_failed_before_staging(
    repository: Path,
    result: subprocess.CompletedProcess[str],
    *required_messages: str,
) -> None:
    assert result.returncode != 0
    combined = _combined_output(result)
    for message in required_messages:
        assert message in combined
    assert not (repository / "dist" / "zigbeelens-hacs").exists()


def _assert_packaged_provenance(
    repository: Path,
    expected_commit: str,
    *,
    source_repository: str = DEFAULT_SOURCE_REPOSITORY,
    future_hacs_repository: str = DEFAULT_FUTURE_HACS_REPOSITORY,
) -> None:
    stage = repository / "dist" / "zigbeelens-hacs"
    assert (stage / "SOURCE_COMMIT").read_bytes() == (
        f"{expected_commit}\n".encode()
    )
    manifest = json.loads(
        (
            stage / "custom_components" / "zigbeelens" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    hacs_documentation = (
        f"https://github.com/{source_repository}/blob/"
        f"{expected_commit}/docs/hacs.md"
    )
    docker_documentation = (
        f"https://github.com/{source_repository}/blob/"
        f"{expected_commit}/docs/docker.md"
    )
    assert manifest["documentation"] == hacs_documentation
    assert manifest["issue_tracker"] == (
        f"https://github.com/{source_repository}/issues"
    )
    assert manifest["single_config_entry"] is True

    readme = (stage / "README.md").read_text(encoding="utf-8")
    local_heading = "## Local staged integration testing"
    future_heading = "## Conditional public HACS installation"
    current_section, future_section = readme.split(future_heading, 1)
    local_section = current_section.split(local_heading, 1)[1]
    expected_commit_link = (
        f"[`{expected_commit}`](https://github.com/{source_repository}/"
        f"commit/{expected_commit})"
    )

    assert readme.count(
        f"[ZigbeeLens Core](https://github.com/{source_repository})"
    ) == 1
    assert f"ghcr.io/{source_repository}" in current_section
    assert local_section.count(expected_commit_link) == 1
    assert local_section.count(hacs_documentation) == 1
    assert current_section.count(docker_documentation) == 1
    assert "/blob/main/docs/" not in current_section
    assert (
        f"https://github.com/{future_hacs_repository}"
        in future_section
    )
    assert f"Issues: https://github.com/{source_repository}/issues" in readme
    assert _expected_pre_sync_readme_block() in readme
    assert json.loads(
        (stage / "pre-sync-evidence.json").read_text(encoding="utf-8")
    ) == EXPECTED_PRE_SYNC_EVIDENCE
    normalized_readme = " ".join(readme.split())
    assert (
        "Synchronization alone does not authorize installation or release"
        in normalized_readme
    )
    assert (
        "`SOURCE_COMMIT` plus the generated Git tree identify this candidate"
        in normalized_readme
    )
    assert "previously unused version" not in readme.lower()
    assert "not synchronized with this stage" not in readme.lower()
    for placeholder in {
        "@SOURCE_COMMIT@",
        "@SOURCE_REPOSITORY@",
        "@FUTURE_HACS_REPOSITORY@",
        *_pre_sync_placeholders(),
        "@GITHUB_OWNER@",
    }:
        assert placeholder not in readme


def _assert_generated_release_contract(stage: Path) -> None:
    matrix = json.loads(
        (stage / "ha-test-matrix.json").read_text(encoding="utf-8")
    )
    assert matrix == EXPECTED_HA_MATRIX
    assert (
        stage / "requirements-test-minimum.txt"
    ).read_text(encoding="utf-8").splitlines() == [
        "-r requirements-test.txt",
        "homeassistant==2025.1.0",
    ]
    assert (
        stage / "requirements-test-current.txt"
    ).read_text(encoding="utf-8").splitlines() == [
        "-r requirements-test.txt",
        "homeassistant==2026.7.3",
    ]
    common_requirements = (
        stage / "requirements-test.txt"
    ).read_text(encoding="utf-8")
    assert re.search(
        r"(?im)^homeassistant(?:$|[\s\[<>=!~;])",
        common_requirements,
    ) is None

    ci = (stage / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert ci.count("workflow_call:") == 1
    assert ci.count("bash scripts/validate-hacs-repo.sh") == 1
    assert ci.count(
        'bash scripts/test-ha-integration-matrix.sh "${{ matrix.lane }}"'
    ) == 1
    assert (
        f"home-assistant/actions/hassfest@{HASSFEST_COMMIT}" in ci
    )
    assert f"hacs/action@{HACS_ACTION_COMMIT}" in ci
    assert ci.count("category: integration") == 1
    assert re.findall(
        r"(?m)^\s+- lane:\s*(\S+)\s*\n"
        r"\s+homeassistant:\s*[\"']([^\"']+)[\"']\s*\n"
        r"\s+python:\s*[\"']([^\"']+)[\"']\s*$",
        ci,
    ) == [
        ("minimum", "2025.1.0", "3.12"),
        ("current", "2026.7.3", "3.14"),
    ]
    hassfest_job = re.search(
        r"(?ms)^  hassfest:[ \t]*\n"
        r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
        ci,
    )
    assert hassfest_job is not None
    assert hassfest_job.group("body").count(
        "uses: actions/checkout@v4"
    ) == 1
    hacs_job = re.search(
        r"(?ms)^  hacs:[ \t]*\n"
        r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
        ci,
    )
    assert hacs_job is not None
    assert re.search(
        r"(?m)^\s{4}permissions:\s*\{\}\s*$",
        hacs_job.group("body"),
    )

    release = (
        stage / ".github/workflows/release.yml"
    ).read_text(encoding="utf-8")
    assert release.count("uses: ./.github/workflows/ci.yml") == 1
    validation_job = re.search(
        r"(?ms)^  validation:[ \t]*\n"
        r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$|\Z)",
        release,
    )
    assert validation_job is not None
    assert re.search(
        r"(?m)^\s{4}uses:\s*\./\.github/workflows/ci\.yml\s*$",
        validation_job.group("body"),
    )
    assert re.search(r"(?m)^\s{4}needs:\s*validation\s*$", release)

    runner = (
        stage / "scripts/test-ha-integration-matrix.sh"
    ).read_text(encoding="utf-8")
    assert "mktemp -d" in runner
    assert 'version("homeassistant")' in runner
    assert (
        '"${venv}/bin/python" -m pytest -q "${HA_DIR}"'
        in runner
    )
    assert ".venv-test" not in runner


def _assert_package_tree_matches_commit(
    repository: Path,
    expected_commit: str,
    *,
    source_repository: str = DEFAULT_SOURCE_REPOSITORY,
    future_hacs_repository: str = DEFAULT_FUTURE_HACS_REPOSITORY,
) -> None:
    stage = repository / "dist" / "zigbeelens-hacs"
    integration_prefix = (
        "apps/ha_integration/custom_components/zigbeelens/"
    )
    integration_sources = _git_text(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        expected_commit,
        "apps/ha_integration/custom_components/zigbeelens",
    ).splitlines()
    integration_test_sources = _git_text(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        expected_commit,
        "apps/ha_integration/tests",
    ).splitlines()
    integration_doc_sources = _git_text(
        repository,
        "ls-tree",
        "-r",
        "--name-only",
        expected_commit,
        "apps/ha_integration/docs",
    ).splitlines()
    expected_stage_files = {
        source.removeprefix("apps/ha_integration/")
        for source in integration_sources
    }
    expected_stage_files.update(
        source.removeprefix("apps/ha_integration/")
        for source in integration_test_sources
    )
    expected_stage_files.update(
        source.removeprefix("apps/ha_integration/")
        for source in integration_doc_sources
    )
    expected_stage_files.update(
        {
            "SOURCE_COMMIT",
            "pre-sync-evidence.json",
            "hacs.json",
            "README.md",
            "LICENSE",
            "CHANGELOG.md",
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            "scripts/validate-hacs-repo.sh",
            "scripts/test-ha-integration-matrix.sh",
            "ha-test-matrix.json",
            "pytest.ini",
            "requirements-test.txt",
            "requirements-test-minimum.txt",
            "requirements-test-current.txt",
            "tests/fixtures/http_origin_vectors.json",
        }
    )
    actual_stage_files = {
        path.relative_to(stage).as_posix()
        for path in stage.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    assert actual_stage_files == expected_stage_files

    manifest_source = (
        "apps/ha_integration/custom_components/zigbeelens/manifest.json"
    )
    for source in integration_sources:
        if source == manifest_source:
            continue
        destination = stage / source.removeprefix("apps/ha_integration/")
        assert destination.read_bytes() == _git_bytes(
            repository,
            "show",
            f"{expected_commit}:{source}",
        )
        assert source.startswith(integration_prefix)

    for source in integration_test_sources:
        destination = stage / source.removeprefix("apps/ha_integration/")
        assert destination.read_bytes() == _git_bytes(
            repository,
            "show",
            f"{expected_commit}:{source}",
        )

    for source in integration_doc_sources:
        destination = stage / source.removeprefix("apps/ha_integration/")
        assert destination.read_bytes() == _git_bytes(
            repository,
            "show",
            f"{expected_commit}:{source}",
        )

    expected_manifest = json.loads(
        _git_bytes(
            repository,
            "show",
            f"{expected_commit}:{manifest_source}",
        )
    )
    expected_manifest["documentation"] = (
        f"https://github.com/{source_repository}/blob/"
        f"{expected_commit}/docs/hacs.md"
    )
    expected_manifest["issue_tracker"] = (
        f"https://github.com/{source_repository}/issues"
    )
    actual_manifest = json.loads(
        (stage / "custom_components/zigbeelens/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert actual_manifest == expected_manifest

    static_files = {
        "LICENSE": "LICENSE",
        "CHANGELOG.md": "CHANGELOG.md",
        (
            "release/zigbeelens-hacs/.github/workflows/ci.yml"
        ): ".github/workflows/ci.yml",
        (
            "release/zigbeelens-hacs/.github/workflows/release.yml"
        ): ".github/workflows/release.yml",
        (
            "scripts/test-ha-integration-matrix.sh"
        ): "scripts/test-ha-integration-matrix.sh",
        (
            "release/zigbeelens-hacs/pre-sync-evidence.json"
        ): "pre-sync-evidence.json",
        "apps/ha_integration/ha-test-matrix.json": "ha-test-matrix.json",
        "apps/ha_integration/pytest.ini": "pytest.ini",
        "apps/ha_integration/requirements-test.txt": "requirements-test.txt",
        (
            "apps/ha_integration/requirements-test-minimum.txt"
        ): "requirements-test-minimum.txt",
        (
            "apps/ha_integration/requirements-test-current.txt"
        ): "requirements-test-current.txt",
        (
            "apps/core/tests/fixtures/http_origin_vectors.json"
        ): "tests/fixtures/http_origin_vectors.json",
    }
    for source, destination in static_files.items():
        assert (stage / destination).read_bytes() == _git_bytes(
            repository,
            "show",
            f"{expected_commit}:{source}",
        )

    template = _git_bytes(
        repository,
        "show",
        (
            f"{expected_commit}:"
            "release/zigbeelens-hacs/README.md.in"
        ),
    ).decode()
    expected_readme = template
    for placeholder, value in (
        ("@SOURCE_REPOSITORY@", source_repository),
        ("@FUTURE_HACS_REPOSITORY@", future_hacs_repository),
        ("@SOURCE_COMMIT@", expected_commit),
        *_pre_sync_placeholders().items(),
    ):
        expected_readme = expected_readme.replace(placeholder, value)
    assert (stage / "README.md").read_text(encoding="utf-8") == expected_readme
    validator_template = _git_bytes(
        repository,
        "show",
        (
            f"{expected_commit}:"
            "release/zigbeelens-hacs/scripts/validate-hacs-repo.sh"
        ),
    ).decode()
    expected_validator = _render_template(
        validator_template,
        _pre_sync_placeholders(),
    )
    assert (
        stage / "scripts" / "validate-hacs-repo.sh"
    ).read_text(encoding="utf-8") == expected_validator
    assert json.loads((stage / "hacs.json").read_text(encoding="utf-8")) == {
        "name": "ZigbeeLens",
        "content_in_root": False,
        "render_readme": True,
        "homeassistant": "2025.1.0",
    }


def test_packager_derives_source_commit_from_git_head(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)

    result = _run_packager(repository)

    assert result.returncode == 0, result.stderr
    _assert_packaged_provenance(repository, head)
    _assert_package_tree_matches_commit(repository, head)


def test_packager_normalizes_source_commit_override(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)

    result = _run_packager(repository, source_commit=head.upper())

    assert result.returncode == 0, result.stderr
    _assert_packaged_provenance(repository, head)


def test_package_validator_accepts_matching_provenance(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    package_result = _run_packager(repository, source_commit=head)
    assert package_result.returncode == 0, package_result.stderr

    validation = _run_package_validator(repository)

    assert validation.returncode == 0, validation.stderr
    assert "SOURCE_COMMIT" in validation.stdout


def test_canonical_pre_sync_hacs_evidence_is_exact() -> None:
    assert json.loads(
        PRE_SYNC_EVIDENCE_SOURCE.read_text(encoding="utf-8")
    ) == EXPECTED_PRE_SYNC_EVIDENCE


def test_generated_hacs_tree_is_deterministic(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    first_result = _run_packager(repository)
    assert first_result.returncode == 0, first_result.stderr
    stage = repository / "dist" / "zigbeelens-hacs"
    first = {
        path.relative_to(stage).as_posix(): (
            path.read_bytes(),
            path.stat().st_mode & 0o777,
        )
        for path in stage.rglob("*")
        if path.is_file()
    }

    second_result = _run_packager(repository)
    assert second_result.returncode == 0, second_result.stderr
    second = {
        path.relative_to(stage).as_posix(): (
            path.read_bytes(),
            path.stat().st_mode & 0o777,
        )
        for path in stage.rglob("*")
        if path.is_file()
    }

    assert second == first


def test_generated_release_infrastructure_is_sealed(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    _assert_generated_release_contract(
        repository / "dist" / "zigbeelens-hacs"
    )


def test_monorepo_release_paths_own_exact_ha_matrix_and_structure() -> None:
    for workflow_path in (CI_WORKFLOW, RELEASE_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        _assert_ha_matrix_job_contract(workflow)
        assert "bash scripts/validate-ha-integration.sh --skip-matrix" in workflow
    _assert_canonical_ha_validator_contract(
        HA_VALIDATOR.read_text(encoding="utf-8")
    )

    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    release_check = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    _assert_downstream_matrix_dependencies(ci, release_check)

    helper = (
        ROOT / "scripts" / "run-release-checks.sh"
    ).read_text(encoding="utf-8")
    structural = helper.index(
        "bash scripts/validate-ha-integration.sh --skip-matrix"
    )
    matrix = helper.index(
        "bash dist/zigbeelens-hacs/scripts/test-ha-integration-matrix.sh"
    )
    live = helper.index("bash scripts/test-enrichment-live-e2e.sh")
    package = helper.index("bash scripts/package-hacs-repo.sh")
    assert structural < matrix < live < package
    assert "pnpm --filter @zigbeelens/shared typecheck" in helper


@pytest.mark.parametrize("workflow_path", (CI_WORKFLOW, RELEASE_WORKFLOW))
@pytest.mark.parametrize(
    ("old", "new"),
    (
        (HACS_PACKAGE_COMMAND, "true"),
        (HACS_VALIDATE_COMMAND, "true"),
        (STAGED_HA_MATRIX_COMMAND, SOURCE_HA_MATRIX_COMMAND),
        (
            STAGED_HA_MATRIX_COMMAND,
            (
                "bash dist/zigbeelens-hacs/scripts/"
                "test-ha-integration-matrix.sh minimum"
            ),
        ),
        (HACS_PACKAGE_COMMAND, f"{HACS_PACKAGE_COMMAND} || true"),
        (HACS_VALIDATE_COMMAND, f"{HACS_VALIDATE_COMMAND} || true"),
        (
            STAGED_HA_MATRIX_COMMAND,
            f"{STAGED_HA_MATRIX_COMMAND} || true",
        ),
        (
            HACS_PACKAGE_COMMAND,
            "test -f dist/zigbeelens-hacs/SOURCE_COMMIT",
        ),
        (
            "uses: actions/checkout@v4",
            (
                "uses: actions/checkout@v4\n"
                "        with:\n"
                "          repository: theaussiepom/zigbeelens-hacs"
            ),
        ),
        (
            "uses: actions/checkout@v4",
            "uses: actions/checkout@v4\n        if: false",
        ),
        (
            "timeout-minutes: 30",
            (
                "timeout-minutes: 30\n"
                "    defaults:\n"
                "      run:\n"
                "        shell: bash {0}; exit 0"
            ),
        ),
        (
            "timeout-minutes: 30",
            (
                "timeout-minutes: 30\n"
                "    env:\n"
                "      ZIGBEELENS_SOURCE_REPOSITORY: "
                "theaussiepom/zigbeelens-hacs"
            ),
        ),
    ),
)
def test_ha_matrix_job_contract_rejects_adversarial_weakening(
    workflow_path: Path,
    old: str,
    new: str,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    weakened = _mutate_ha_matrix_job(workflow, old, new)
    with pytest.raises(AssertionError):
        _assert_ha_matrix_job_contract(weakened)


@pytest.mark.parametrize("workflow_path", (CI_WORKFLOW, RELEASE_WORKFLOW))
def test_ha_matrix_job_contract_rejects_global_success_shell(
    workflow_path: Path,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    weakened = (
        "defaults:\n"
        "  run:\n"
        "    shell: bash {0}; exit 0\n"
        f"{workflow}"
    )
    with pytest.raises(AssertionError):
        _assert_ha_matrix_job_contract(weakened)


@pytest.mark.parametrize("workflow_path", (CI_WORKFLOW, RELEASE_WORKFLOW))
def test_ha_matrix_job_contract_rejects_matrix_before_validation(
    workflow_path: Path,
) -> None:
    workflow = workflow_path.read_text(encoding="utf-8")
    body = _job_body(workflow, HA_MATRIX_JOB_NAME)
    weakened_body = _swap_once(
        body,
        HACS_VALIDATE_COMMAND,
        STAGED_HA_MATRIX_COMMAND,
    )
    weakened = workflow.replace(body, weakened_body, 1)
    with pytest.raises(AssertionError):
        _assert_ha_matrix_job_contract(weakened)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (LOCAL_HACS_PACKAGE_COMMAND, "true"),
        (LOCAL_HACS_VALIDATE_COMMAND, "true"),
        (
            LOCAL_STAGED_HA_MATRIX_COMMAND,
            LOCAL_SOURCE_HA_MATRIX_COMMAND,
        ),
        (
            LOCAL_STAGED_HA_MATRIX_COMMAND,
            f"{LOCAL_STAGED_HA_MATRIX_COMMAND} minimum",
        ),
        (
            LOCAL_HACS_PACKAGE_COMMAND,
            f"{LOCAL_HACS_PACKAGE_COMMAND} || true",
        ),
        (
            LOCAL_HACS_VALIDATE_COMMAND,
            f"{LOCAL_HACS_VALIDATE_COMMAND} || true",
        ),
        (
            LOCAL_STAGED_HA_MATRIX_COMMAND,
            f"{LOCAL_STAGED_HA_MATRIX_COMMAND} || true",
        ),
        (
            LOCAL_HACS_PACKAGE_COMMAND,
            'test -f "${ROOT}/dist/zigbeelens-hacs/SOURCE_COMMIT"',
        ),
        (
            "set -euo pipefail",
            (
                "set -euo pipefail\n"
                "git clone "
                "https://github.com/theaussiepom/zigbeelens-hacs"
            ),
        ),
        (
            "set -euo pipefail",
            "set -euo pipefail\nset +e",
        ),
        (
            'if [[ "${SKIP_MATRIX}" -eq 0 ]]; then',
            'if [[ "${SKIP_MATRIX}" -eq 1 ]]; then',
        ),
    ),
)
def test_canonical_ha_validator_rejects_adversarial_weakening(
    old: str,
    new: str,
) -> None:
    validator = HA_VALIDATOR.read_text(encoding="utf-8")
    assert old in validator
    weakened = validator.replace(old, new, 1)
    with pytest.raises(AssertionError):
        _assert_canonical_ha_validator_contract(weakened)


def test_canonical_ha_validator_rejects_matrix_before_validation() -> None:
    validator = HA_VALIDATOR.read_text(encoding="utf-8")
    weakened = _swap_once(
        validator,
        LOCAL_HACS_VALIDATE_COMMAND,
        LOCAL_STAGED_HA_MATRIX_COMMAND,
    )
    with pytest.raises(AssertionError):
        _assert_canonical_ha_validator_contract(weakened)


def test_canonical_ha_validator_rejects_packaging_inside_matrix_gate() -> None:
    validator = HA_VALIDATOR.read_text(encoding="utf-8")
    weakened = validator.replace(
        f"{LOCAL_HACS_PACKAGE_COMMAND}\n",
        "",
        1,
    ).replace(
        f"{LOCAL_HACS_VALIDATE_COMMAND}\n",
        "",
        1,
    )
    gate = 'if [[ "${SKIP_MATRIX}" -eq 0 ]]; then'
    weakened = weakened.replace(
        gate,
        (
            f"{gate}\n"
            f"  {LOCAL_HACS_PACKAGE_COMMAND}\n"
            f"  {LOCAL_HACS_VALIDATE_COMMAND}"
        ),
        1,
    )
    with pytest.raises(AssertionError):
        _assert_canonical_ha_validator_contract(weakened)


@pytest.mark.parametrize(
    ("workflow_path", "job_name"),
    (
        (CI_WORKFLOW, "packaging"),
        (RELEASE_WORKFLOW, "release-gate"),
    ),
)
def test_downstream_job_contract_rejects_missing_matrix_dependency(
    workflow_path: Path,
    job_name: str,
) -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    workflow = ci if workflow_path == CI_WORKFLOW else release
    body = _job_body(workflow, job_name)
    weakened_body = body.replace("ha-integration-matrix", "matrix-decoy", 1)
    assert weakened_body != body
    weakened = workflow.replace(body, weakened_body, 1)

    with pytest.raises(AssertionError):
        _assert_downstream_matrix_dependencies(
            weakened if workflow_path == CI_WORKFLOW else ci,
            weakened if workflow_path == RELEASE_WORKFLOW else release,
        )


def test_package_validator_rejects_missing_single_config_entry(
    tmp_path: Path,
):
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    manifest_path = (
        repository
        / "dist"
        / "zigbeelens-hacs"
        / "custom_components"
        / "zigbeelens"
        / "manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("single_config_entry")
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "single_config_entry must be true" in _combined_output(validation)


def test_package_validator_rejects_moving_hassfest_reference(
    tmp_path: Path,
):
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    workflow_path = (
        repository
        / "dist"
        / "zigbeelens-hacs"
        / ".github"
        / "workflows"
        / "ci.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(
        workflow.replace(HASSFEST_COMMIT, "master", 1),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "hassfest@" in _combined_output(validation)


def test_package_validator_rejects_ungated_release(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    workflow_path = (
        repository
        / "dist"
        / "zigbeelens-hacs"
        / ".github"
        / "workflows"
        / "release.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")
    workflow_path.write_text(
        workflow.replace("    needs: validation\n", "", 1),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "publish job must depend on validation" in _combined_output(validation)


def test_generated_operational_documentation_is_pinned(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme = (
        repository / "dist" / "zigbeelens-hacs" / "README.md"
    ).read_text(encoding="utf-8")
    current_section = readme.split(
        "## Conditional public HACS installation",
        1,
    )[0]

    assert f"/blob/{head}/docs/hacs.md" in current_section
    assert f"/blob/{head}/docs/docker.md" in current_section
    assert "/blob/main/docs/" not in current_section


@pytest.mark.parametrize(
    "invalid",
    (
        "a" * 39,
        "a" * 41,
        "g" * 40,
        ("a" * 20) + "\n" + ("b" * 20),
    ),
)
def test_packager_rejects_invalid_source_commit_override(
    tmp_path: Path,
    invalid: str,
):
    repository = _fixture_repository(tmp_path)

    result = _run_packager(repository, source_commit=invalid)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "must be exactly 40 hexadecimal characters",
    )


def test_packager_rejects_nonexistent_source_commit(tmp_path: Path):
    repository = _fixture_repository(tmp_path)

    result = _run_packager(repository, source_commit="b" * 40)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "does not identify an existing commit",
    )


def test_packager_rejects_different_existing_source_commit(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    previous_commit = _head(repository)
    (repository / "unrelated-marker.txt").write_text(
        "second commit\n",
        encoding="utf-8",
    )
    _commit_all(repository, "second fixture commit")

    result = _run_packager(repository, source_commit=previous_commit)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "does not match checked-out HEAD",
    )


def test_packager_rejects_dirty_integration_source(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    integration = (
        repository
        / "apps"
        / "ha_integration"
        / "custom_components"
        / "zigbeelens"
        / "api.py"
    )
    integration.write_text(
        integration.read_text(encoding="utf-8") + "\n# dirty source\n",
        encoding="utf-8",
    )

    result = _run_packager(repository)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "tracked package inputs differ from SOURCE_COMMIT",
    )


def test_packager_rejects_dirty_readme_template(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    template = repository / "release" / "zigbeelens-hacs" / "README.md.in"
    template.write_text(
        template.read_text(encoding="utf-8") + "\nDirty template.\n",
        encoding="utf-8",
    )

    result = _run_packager(repository)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "tracked package inputs differ from SOURCE_COMMIT",
    )


@pytest.mark.parametrize(
    "mutation",
    ("missing", "malformed", "duplicate", "extra", "wrong_version"),
)
def test_packager_rejects_invalid_canonical_pre_sync_evidence(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = _fixture_repository(tmp_path)
    evidence_path = (
        repository / "release" / "zigbeelens-hacs"
        / "pre-sync-evidence.json"
    )
    if mutation == "missing":
        evidence_path.unlink()
    elif mutation == "malformed":
        evidence_path.write_text("{", encoding="utf-8")
    elif mutation == "duplicate":
        evidence_path.write_text(
            evidence_path.read_text(encoding="utf-8").replace(
                "{\n",
                '{\n  "repository": "duplicate/identity",\n',
                1,
            ),
            encoding="utf-8",
        )
    else:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if mutation == "extra":
            evidence["extra"] = "forbidden"
        else:
            evidence["manifest_version"] = "0.1.15"
            evidence["release_tag"] = "v0.1.15"
        evidence_path.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )
    _commit_all(repository, f"mutate evidence: {mutation}")

    result = _run_packager(repository)

    assert result.returncode != 0
    assert not (repository / "dist" / "zigbeelens-hacs").exists()


def test_packager_rejects_unresolved_template_placeholder(
    tmp_path: Path,
) -> None:
    repository = _fixture_repository(tmp_path)
    template = repository / "release" / "zigbeelens-hacs" / "README.md.in"
    template.write_text(
        template.read_text(encoding="utf-8")
        + "\n@PRE_SYNC_HACS_UNKNOWN@\n",
        encoding="utf-8",
    )
    _commit_all(repository, "add unresolved evidence placeholder")

    result = _run_packager(repository)

    assert result.returncode != 0
    assert "unknown placeholder" in _combined_output(result)
    assert not (repository / "dist" / "zigbeelens-hacs").exists()


@pytest.mark.parametrize(
    "relative",
    (
        "release/zigbeelens-hacs/README.md.in",
        "release/zigbeelens-hacs/scripts/validate-hacs-repo.sh",
    ),
    ids=("readme", "validator"),
)
def test_packager_rejects_duplicate_evidence_placeholder(
    tmp_path: Path,
    relative: str,
) -> None:
    repository = _fixture_repository(tmp_path)
    template = repository / relative
    template.write_text(
        template.read_text(encoding="utf-8")
        + "\nMirror tree: @PRE_SYNC_HACS_TREE@\n",
        encoding="utf-8",
    )
    _commit_all(repository, "duplicate evidence placeholder")

    result = _run_packager(repository)

    assert result.returncode != 0
    assert "duplicated or misplaced placeholder" in _combined_output(result)
    assert not (repository / "dist" / "zigbeelens-hacs").exists()


@pytest.mark.parametrize(
    "relative",
    (
        "LICENSE",
        "CHANGELOG.md",
        "release/zigbeelens-hacs/.github/workflows/ci.yml",
        "release/zigbeelens-hacs/.github/workflows/release.yml",
        "release/zigbeelens-hacs/pre-sync-evidence.json",
        "release/zigbeelens-hacs/scripts/validate-hacs-repo.sh",
        "apps/ha_integration/ha-test-matrix.json",
        "apps/ha_integration/docs/zigbeelens-icon.svg",
        "apps/ha_integration/requirements-test-current.txt",
        "apps/ha_integration/tests/test_matrix_contract.py",
        "apps/core/tests/fixtures/http_origin_vectors.json",
        "scripts/package-hacs-repo.sh",
        "scripts/test-ha-integration-matrix.sh",
    ),
)
def test_packager_rejects_other_dirty_package_input(
    tmp_path: Path,
    relative: str,
):
    repository = _fixture_repository(tmp_path)
    package_input = repository / relative
    package_input.write_text(
        package_input.read_text(encoding="utf-8") + "\n# dirty input\n",
        encoding="utf-8",
    )

    result = _run_packager(repository)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "tracked package inputs differ from SOURCE_COMMIT",
    )


def test_packager_rejects_untracked_integration_source(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    untracked = (
        repository
        / "apps"
        / "ha_integration"
        / "custom_components"
        / "zigbeelens"
        / "debug-secret.py"
    )
    untracked.write_text("DEBUG_TOKEN = 'must-not-ship'\n", encoding="utf-8")

    result = _run_packager(repository)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "untracked package inputs are not present in SOURCE_COMMIT",
    )


def test_ignored_generated_source_is_not_packaged(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    ignored = (
        repository
        / "apps"
        / "ha_integration"
        / "custom_components"
        / "zigbeelens"
        / "__pycache__"
        / "debug.cpython-312.pyc"
    )
    ignored.parent.mkdir(parents=True)
    ignored.write_bytes(b"not bytecode")

    result = _run_packager(repository)

    assert result.returncode == 0, result.stderr
    stage = repository / "dist" / "zigbeelens-hacs"
    assert not list(stage.rglob("__pycache__"))
    assert not list(stage.rglob("*.pyc"))


def test_packager_requires_git_checkout(tmp_path: Path):
    repository = tmp_path / "not-a-git-checkout"
    _copy_fixture_files(repository)

    result = _run_packager(repository)

    _assert_packager_failed_before_staging(
        repository,
        result,
        "package source root must be the exact root of a Git checkout",
    )


def test_package_validator_rejects_moving_current_documentation_link(
    tmp_path: Path,
):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    pinned = f"/blob/{head}/docs/docker.md"
    readme = readme_path.read_text(encoding="utf-8")
    assert pinned in readme
    readme_path.write_text(
        readme.replace(pinned, "/blob/main/docs/docker.md", 1),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert (
        "README pinned Docker documentation URL does not match "
        "SOURCE_COMMIT/source repository"
    ) in _combined_output(validation)


@pytest.mark.parametrize(
    "surface",
    ("hacs_documentation", "docker_documentation", "docker_image", "issues"),
)
def test_package_validator_rejects_operational_url_suffix(
    tmp_path: Path,
    surface: str,
):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    expected_values = {
        "hacs_documentation": (
            f"https://github.com/{DEFAULT_SOURCE_REPOSITORY}/blob/"
            f"{head}/docs/hacs.md"
        ),
        "docker_documentation": (
            f"https://github.com/{DEFAULT_SOURCE_REPOSITORY}/blob/"
            f"{head}/docs/docker.md"
        ),
        "docker_image": f"ghcr.io/{DEFAULT_SOURCE_REPOSITORY}",
        "issues": f"https://github.com/{DEFAULT_SOURCE_REPOSITORY}/issues",
    }
    expected = expected_values[surface]
    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    assert expected in readme
    readme_path.write_text(
        readme.replace(expected, f"{expected}.evil", 1),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0


@pytest.mark.parametrize(
    "surface",
    (
        "core_repository",
        "docker_image",
        "issues",
        "package_commit",
        "pre_sync_evidence",
    ),
)
def test_package_validator_rejects_conflicting_source_identity_decoy(
    tmp_path: Path,
    surface: str,
):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    decoys = {
        "core_repository": (
            "[ZigbeeLens Core](https://github.com/impostor/zigbeelens)"
        ),
        "docker_image": "`ghcr.io/impostor/zigbeelens`",
        "issues": "Issues: https://github.com/impostor/zigbeelens/issues",
        "package_commit": (
            f"[`{head}`](https://github.com/impostor/zigbeelens/"
            f"commit/{head})"
        ),
        "pre_sync_evidence": (
            "Pre-synchronization historical evidence:\n\n"
            "- repository: `impostor/zigbeelens-hacs`\n"
            f"- commit: `{EXPECTED_PRE_SYNC_EVIDENCE['commit']}`\n"
            f"- tree: `{EXPECTED_PRE_SYNC_EVIDENCE['tree']}`\n"
            "- `SOURCE_COMMIT`: "
            f"`{EXPECTED_PRE_SYNC_EVIDENCE['source_commit']}`\n"
            "- manifest version: "
            f"`{EXPECTED_PRE_SYNC_EVIDENCE['manifest_version']}`\n"
            f"- reviewed: `{EXPECTED_PRE_SYNC_EVIDENCE['reviewed_on']}`\n"
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` tag: absent\n"
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` release: absent"
        ),
    }
    decoy = decoys[surface]
    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    future_heading = "## Conditional public HACS installation"
    assert future_heading in readme
    readme_path.write_text(
        readme.replace(
            future_heading,
            "Conflicting source identity decoy:\n\n"
            f"{decoy}\n\n{future_heading}",
            1,
        ),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0


@pytest.mark.parametrize(
    "mismatch_surface",
    ("manifest", "readme", "source_file"),
)
def test_package_validator_rejects_source_commit_mismatch(
    tmp_path: Path,
    mismatch_surface: str,
):
    repository = _fixture_repository(tmp_path)
    source_commit = _head(repository)
    mismatched_commit = "c" * 40
    package_result = _run_packager(
        repository,
        source_commit=source_commit,
    )
    assert package_result.returncode == 0, package_result.stderr

    stage = repository / "dist" / "zigbeelens-hacs"
    if mismatch_surface == "manifest":
        manifest_path = (
            stage / "custom_components" / "zigbeelens" / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documentation"] = manifest["documentation"].replace(
            source_commit,
            mismatched_commit,
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
    elif mismatch_surface == "readme":
        readme_path = stage / "README.md"
        readme = readme_path.read_text(encoding="utf-8").replace(
            source_commit,
            mismatched_commit,
        )
        readme += (
            "\nDecoy package provenance outside the local-stage section:\n"
            f"[`{source_commit}`](https://github.com/"
            f"{DEFAULT_SOURCE_REPOSITORY}/commit/{source_commit})\n"
            f"https://github.com/{DEFAULT_SOURCE_REPOSITORY}/blob/"
            f"{source_commit}/docs/hacs.md\n"
        )
        readme_path.write_text(readme, encoding="utf-8")
    else:
        (stage / "SOURCE_COMMIT").write_text(
            f"{mismatched_commit}\n",
            encoding="utf-8",
        )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "SOURCE_COMMIT" in _combined_output(validation)


def test_package_validator_rejects_pre_sync_satellite_identity_mismatch(
    tmp_path: Path,
):
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme_path.write_text(
        readme.replace(
            f"- repository: `{EXPECTED_PRE_SYNC_EVIDENCE['repository']}`",
            "- repository: `different-owner/different-satellite`",
            1,
        ),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "pre-synchronization evidence" in _combined_output(validation)


@pytest.mark.parametrize(
    ("owned_line", "replacement"),
    (
        (
            f"- commit: `{EXPECTED_PRE_SYNC_EVIDENCE['commit']}`",
            f"- commit: `{'c' * 40}`",
        ),
        (
            f"- tree: `{EXPECTED_PRE_SYNC_EVIDENCE['tree']}`",
            f"- tree: `{'a' * 40}`",
        ),
        (
            "- `SOURCE_COMMIT`: "
            f"`{EXPECTED_PRE_SYNC_EVIDENCE['source_commit']}`",
            f"- `SOURCE_COMMIT`: `{'b' * 40}`",
        ),
        (
            "- manifest version: "
            f"`{EXPECTED_PRE_SYNC_EVIDENCE['manifest_version']}`",
            "- manifest version: `0.1.15`",
        ),
        (
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` tag: absent\n",
            "",
        ),
        (
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` release: absent",
            "",
        ),
        (
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` tag: absent",
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` tag: present",
        ),
        (
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` release: absent",
            f"- `{EXPECTED_PRE_SYNC_EVIDENCE['release_tag']}` release: present",
        ),
    ),
    ids=(
        "wrong_commit",
        "wrong_tree",
        "wrong_source_commit",
        "wrong_manifest_version",
        "missing_tag_state",
        "missing_release_state",
        "tag_present",
        "release_present",
    ),
)
def test_package_validator_rejects_pre_sync_evidence_mismatch(
    tmp_path: Path,
    owned_line: str,
    replacement: str,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    assert owned_line in readme
    readme_path.write_text(
        readme.replace(owned_line, replacement, 1),
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "pre-synchronization" in _combined_output(validation)


@pytest.mark.parametrize(
    "stale_claim",
    (
        "Reviewed public-satellite state (historical evidence):\n\n"
        "- repository: `theaussiepom/zigbeelens-hacs`\n"
        "- commit: `050d118b3e1406343255594fe64cd569e2420888`\n"
        "- reviewed: `2026-07-23`\n",
        "This candidate uses a previously unused version.",
        "The public satellite is not synchronized with this stage.",
        "The public satellite has not yet been synchronized to this stage.",
        "Do not use the unsynchronized public satellite.",
        "The public satellite remains unsynchronized from this stage.",
        "Manifest version alone uniquely identifies this candidate tree.",
        "Manifest version uniquely identifies this candidate.",
        "This candidate is uniquely identified by manifest version.",
    ),
    ids=(
        "obsolete_050d118_only_evidence",
        "previously_unused_version",
        "not_synchronized",
        "not_yet_synchronized",
        "unsynchronized_satellite",
        "satellite_remains_unsynchronized",
        "version_only_identity",
        "manifest_version_unique_identity",
        "reverse_version_only_identity",
    ),
)
def test_package_validator_rejects_obsolete_pre_release_claim(
    tmp_path: Path,
    stale_claim: str,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8") + "\n" + stale_claim,
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert (
        "stale pre-release synchronization or version-only identity"
        in _combined_output(validation)
    )


def test_package_validator_rejects_duplicate_pre_sync_evidence_block(
    tmp_path: Path,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8")
        + "\n\n"
        + _expected_pre_sync_readme_block()
        + "\n",
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "exactly one complete" in _combined_output(validation)


def test_package_validator_rejects_unresolved_readme_placeholder(
    tmp_path: Path,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8")
        + "\n@PRE_SYNC_HACS_UNRESOLVED@\n",
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "unresolved template placeholder" in _combined_output(validation)


@pytest.mark.parametrize(
    "mutation",
    ("missing", "malformed", "duplicate", "extra", "inconsistent"),
)
def test_package_validator_rejects_invalid_pre_sync_evidence_file(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    evidence_path = (
        repository / "dist" / "zigbeelens-hacs"
        / "pre-sync-evidence.json"
    )
    if mutation == "missing":
        evidence_path.unlink()
    elif mutation == "malformed":
        evidence_path.write_text("{", encoding="utf-8")
    elif mutation == "duplicate":
        evidence_path.write_text(
            evidence_path.read_text(encoding="utf-8").replace(
                "{\n",
                '{\n  "repository": "duplicate/identity",\n',
                1,
            ),
            encoding="utf-8",
        )
    else:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if mutation == "extra":
            evidence["extra"] = "forbidden"
        else:
            evidence["tree"] = "c" * 40
        evidence_path.write_text(
            json.dumps(evidence, indent=2) + "\n",
            encoding="utf-8",
        )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0


def test_package_validator_accepts_future_synchronized_tree_wording(
    tmp_path: Path,
) -> None:
    repository = _fixture_repository(tmp_path)
    package_result = _run_packager(repository)
    assert package_result.returncode == 0, package_result.stderr

    readme_path = repository / "dist" / "zigbeelens-hacs" / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8")
        + "\nAfter synchronization, the exact generated tree is the reviewed "
        "satellite tree; its presence still does not authorize release.\n",
        encoding="utf-8",
    )

    validation = _run_package_validator(repository)

    assert validation.returncode == 0, validation.stderr


def test_packager_separates_nondefault_repository_identities(
    tmp_path: Path,
):
    repository = _fixture_repository(tmp_path)
    head = _head(repository)
    source_repository = "fork-owner/zigbeelens-fork"
    future_hacs_repository = "destination/zigbeelens-hacs-next"

    result = _run_packager(
        repository,
        source_repository=source_repository,
        future_hacs_repository=future_hacs_repository,
    )

    assert result.returncode == 0, result.stderr
    _assert_packaged_provenance(
        repository,
        head,
        source_repository=source_repository,
        future_hacs_repository=future_hacs_repository,
    )
    _assert_package_tree_matches_commit(
        repository,
        head,
        source_repository=source_repository,
        future_hacs_repository=future_hacs_repository,
    )
    readme = (
        repository / "dist" / "zigbeelens-hacs" / "README.md"
    ).read_text(encoding="utf-8")
    current_section, future_section = readme.split(
        "## Conditional public HACS installation",
        1,
    )
    assert f"https://github.com/{future_hacs_repository}" not in current_section
    assert f"https://github.com/{future_hacs_repository}" in future_section
    assert EXPECTED_PRE_SYNC_EVIDENCE["repository"] in current_section

    validation = _run_package_validator(repository)
    assert validation.returncode == 0, validation.stderr


@pytest.mark.parametrize(
    ("variable", "invalid"),
    (
        ("source", ""),
        ("source", "owner-only"),
        ("source", "/repository"),
        ("source", "owner/"),
        ("source", "owner/repository/extra"),
        ("source", "https://github.com/owner/repository"),
        ("source", "owner name/repository"),
        ("source", "owner/repository name"),
        ("future", ""),
        ("future", "owner-only"),
        ("future", "/repository"),
        ("future", "owner/"),
        ("future", "owner/repository/extra"),
        ("future", "https://github.com/owner/repository"),
        ("future", "owner name/repository"),
        ("future", "owner/repository name"),
    ),
)
def test_packager_rejects_invalid_repository_identifier(
    tmp_path: Path,
    variable: str,
    invalid: str,
):
    repository = _fixture_repository(tmp_path)

    if variable == "source":
        result = _run_packager(repository, source_repository=invalid)
        variable_name = "ZIGBEELENS_SOURCE_REPOSITORY"
    else:
        result = _run_packager(
            repository,
            future_hacs_repository=invalid,
        )
        variable_name = "ZIGBEELENS_FUTURE_HACS_REPOSITORY"

    _assert_packager_failed_before_staging(
        repository,
        result,
        variable_name,
        "must be an exact owner/repository identifier",
    )


@pytest.mark.parametrize("legacy_owner", ("", "legacy-owner"))
def test_packager_rejects_legacy_github_owner(
    tmp_path: Path,
    legacy_owner: str,
):
    repository = _fixture_repository(tmp_path)

    result = _run_packager(
        repository,
        legacy_github_owner=legacy_owner,
    )

    _assert_packager_failed_before_staging(
        repository,
        result,
        "GITHUB_OWNER is no longer supported",
        "ZIGBEELENS_SOURCE_REPOSITORY",
        "ZIGBEELENS_FUTURE_HACS_REPOSITORY",
    )
