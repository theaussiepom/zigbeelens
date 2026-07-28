"""Fail-closed contracts for release identity in Docker image metadata."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BUILD_SCRIPT = ROOT / "scripts" / "build-docker.sh"
SMOKE_SCRIPT = ROOT / "scripts" / "smoke-docker.sh"
DOCKERFILE = ROOT / "deploy" / "docker" / "Dockerfile"
VALIDATOR = ROOT / "deploy" / "docker" / "validate_oci_metadata.py"
SPEC = importlib.util.spec_from_file_location(
    "zigbeelens_validate_oci_metadata_contract",
    VALIDATOR,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR_MODULE
SPEC.loader.exec_module(VALIDATOR_MODULE)

MetadataValidationError = VALIDATOR_MODULE.MetadataValidationError
OCI_REVISION_LABEL = VALIDATOR_MODULE.OCI_REVISION_LABEL
OCI_SOURCE_LABEL = VALIDATOR_MODULE.OCI_SOURCE_LABEL
OCI_VERSION_LABEL = VALIDATOR_MODULE.OCI_VERSION_LABEL
validated_labels_from_json = VALIDATOR_MODULE.validated_labels_from_json

PACKAGE_VERSION = "0.1.14"
FULL_REVISION = "906527063ad8bd594fbec51f69f6fc72205302dd"
IMAGE_SOURCE = "https://github.com/theaussiepom/zigbeelens"

VERSION_EXPRESSION = "${{ steps.version.outputs.value }}"
REVISION_EXPRESSION = "${{ github.sha }}"
SOURCE_EXPRESSION = "https://github.com/${{ github.repository }}"
METADATA_JSON_EXPRESSION = "${{ steps.meta.outputs.json }}"
VALIDATED_LABELS_EXPRESSION = "${{ steps.validated-metadata.outputs.labels }}"
PUSH_EXPRESSION = (
    "${{ github.event_name != 'pull_request' && "
    "(github.ref == 'refs/heads/main' || "
    "(startsWith(github.ref, 'refs/tags/v') && "
    "steps.tag-live-e2e.outcome == 'success')) && "
    "github.repository == format('{0}/zigbeelens', "
    "github.repository_owner) }}"
)
TAG_RULES = (
    "type=raw,value=edge,enable=${{ github.event_name == 'push' "
    "&& github.ref == 'refs/heads/main' }}",
    "type=raw,value=main,enable=${{ github.event_name == 'push' "
    "&& github.ref == 'refs/heads/main' }}",
    "type=semver,pattern={{version}}",
    "type=semver,pattern={{major}}.{{minor}}",
    "type=sha,prefix=sha-,format=short",
    "type=raw,value=latest,enable=${{ startsWith(github.ref, 'refs/tags/v') }}",
)


def _step_body(workflow: str, step_name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name:\s*{re.escape(step_name)}\s*\n"
        rf".*?(?=^      - (?:name:|uses:)|\Z)",
        workflow,
    )
    assert match is not None, f"missing workflow step: {step_name}"
    return match.group(0)


def _metadata_payload(
    *,
    labels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tags": [
            "ghcr.io/theaussiepom/zigbeelens:edge",
            "ghcr.io/theaussiepom/zigbeelens:sha-9065270",
        ],
        "labels": labels
        or {
            "org.opencontainers.image.created": "2026-07-27T00:00:00Z",
            "org.opencontainers.image.description": ("Read-only observability console"),
            OCI_VERSION_LABEL: PACKAGE_VERSION,
            OCI_REVISION_LABEL: FULL_REVISION,
            OCI_SOURCE_LABEL: IMAGE_SOURCE,
        },
    }


def _local_build_fixture(
    tmp_path: Path,
    *,
    package_version: str = PACKAGE_VERSION,
) -> tuple[Path, Path, Path]:
    checkout = tmp_path / "checkout"
    scripts = checkout / "scripts"
    docker_dir = checkout / "deploy" / "docker"
    scripts.mkdir(parents=True)
    docker_dir.mkdir(parents=True)
    shutil.copy2(BUILD_SCRIPT, scripts / "build-docker.sh")
    shutil.copy2(DOCKERFILE, docker_dir / "Dockerfile")
    (checkout / "package.json").write_text(
        json.dumps(
            {
                "name": "zigbeelens-local-build-contract",
                "version": package_version,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf "%s\\n" "$@" > "${DOCKER_ARGS_FILE:?}"\n',
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    return checkout, fake_bin, tmp_path / "docker-args"


def _run_local_build(
    checkout: Path,
    fake_bin: Path,
    docker_args: Path,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    build_environment = os.environ.copy()
    for name in (
        "ZIGBEELENS_IMAGE",
        "ZIGBEELENS_REVISION",
        "ZIGBEELENS_VERSION",
    ):
        build_environment.pop(name, None)
    build_environment.update(
        {
            "DOCKER_ARGS_FILE": str(docker_args),
            "PATH": f"{fake_bin}{os.pathsep}{build_environment['PATH']}",
            "ZIGBEELENS_IMAGE": "zigbeelens:contract",
        }
    )
    if environment is not None:
        build_environment.update(environment)
    return subprocess.run(
        ["bash", checkout / "scripts" / "build-docker.sh"],
        cwd=checkout,
        env=build_environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(checkout: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _initialise_git_checkout(checkout: Path) -> str:
    _git(checkout, "init", "--quiet")
    _git(checkout, "add", ".")
    _git(
        checkout,
        "-c",
        "user.name=ZigbeeLens contract",
        "-c",
        "user.email=contracts@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return _git(checkout, "rev-parse", "HEAD")


def _expected_local_build_arguments(revision: str) -> list[str]:
    return [
        "build",
        "-f",
        "deploy/docker/Dockerfile",
        "--build-arg",
        f"VERSION={PACKAGE_VERSION}",
        "--build-arg",
        f"REVISION={revision}",
        "--build-arg",
        f"IMAGE_SOURCE={IMAGE_SOURCE}",
        "-t",
        "zigbeelens:contract",
        "-t",
        f"ghcr.io/theaussiepom/zigbeelens:{PACKAGE_VERSION}",
        ".",
    ]


def _recorded_docker_arguments(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _assert_workflow_contract(workflow: str) -> None:
    assert re.search(
        r"(?ms)^on:\s*\n"
        r"\s+workflow_dispatch:\s*$.*?"
        r"^  pull_request:\s*\n"
        r"\s+branches:\s*\[main,\s*master\]\s*$.*?"
        r"^  push:\s*\n"
        r"\s+branches:\s*\[main,\s*master\]\s*\n"
        r"\s+tags:\s*\n"
        r'\s+-\s+"v\*"\s*$',
        workflow,
    )

    deployment_tests = _step_body(workflow, "Deployment tests")
    read_version = _step_body(workflow, "Read package version")
    metadata = _step_body(workflow, "Docker metadata")
    validate = _step_body(workflow, "Validate Docker metadata labels")
    live_e2e = _step_body(
        workflow,
        "Run canonical live enrichment E2E before tag publication",
    )
    build = _step_body(workflow, "Build and push")

    ordered = (
        "- name: Read package version",
        "- name: Docker metadata",
        "- name: Validate Docker metadata labels",
        "- name: Run canonical live enrichment E2E before tag publication",
        "- name: Build and push",
    )
    positions = [workflow.index(fragment) for fragment in ordered]
    assert positions == sorted(positions)

    assert deployment_tests.count("apps/core/tests/contracts/test_docker_metadata_contract.py") == 1
    assert deployment_tests.count("apps/core/tests/test_docker_deploy.py") == 1
    assert deployment_tests.count("apps/core/tests/test_logging_config.py") == 1

    assert read_version.count("id: version") == 1
    assert read_version.count("package.json") == 1
    assert read_version.count('"$GITHUB_OUTPUT"') == 1

    assert metadata.count("id: meta") == 1
    assert metadata.count("uses: docker/metadata-action@v5") == 1
    for rule in TAG_RULES:
        assert metadata.count(rule) == 1
    assert metadata.count(f"{OCI_VERSION_LABEL}={VERSION_EXPRESSION}") == 1
    assert metadata.count(f"{OCI_REVISION_LABEL}={REVISION_EXPRESSION}") == 1
    assert metadata.count(f"{OCI_SOURCE_LABEL}={SOURCE_EXPRESSION}") == 1

    assert validate.count("id: validated-metadata") == 1
    assert validate.count(f"DOCKER_METADATA_OUTPUT_JSON: {METADATA_JSON_EXPRESSION}") == 1
    assert validate.count(f"EXPECTED_OCI_VERSION: {VERSION_EXPRESSION}") == 1
    assert validate.count(f"EXPECTED_OCI_REVISION: {REVISION_EXPRESSION}") == 1
    assert validate.count(f"EXPECTED_OCI_SOURCE: {SOURCE_EXPRESSION}") == 1
    assert validate.rstrip().endswith("run: python3 deploy/docker/validate_oci_metadata.py")

    assert live_e2e.count("if: startsWith(github.ref, 'refs/tags/v')") == 1
    assert live_e2e.count("id: tag-live-e2e") == 1
    assert live_e2e.rstrip().endswith("run: bash scripts/test-enrichment-live-e2e.sh")

    assert build.count("uses: docker/build-push-action@v6") == 1
    assert build.count("platforms: linux/amd64,linux/arm64") == 1
    assert build.count("tags: ${{ steps.meta.outputs.tags }}") == 1
    assert build.count(f"labels: {VALIDATED_LABELS_EXPRESSION}") == 1
    assert "labels: ${{ steps.meta.outputs.labels }}" not in build
    assert build.count(f"VERSION={VERSION_EXPRESSION}") == 1
    assert build.count(f"REVISION={REVISION_EXPRESSION}") == 1
    assert build.count(f"IMAGE_SOURCE={SOURCE_EXPRESSION}") == 1
    assert build.count(f"push: {PUSH_EXPRESSION}") == 1

    metadata_to_build = workflow[
        workflow.index("- name: Docker metadata") : workflow.index("- name: Build and push")
    ]
    lowered = metadata_to_build.lower()
    for weakening in (
        "continue-on-error:",
        "|| true",
        "if: false",
        "run: true",
        "run: echo",
    ):
        assert weakening not in lowered


def test_docker_workflow_seals_release_metadata() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["version"] == PACKAGE_VERSION
    _assert_workflow_contract(WORKFLOW.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            f"{OCI_VERSION_LABEL}={VERSION_EXPRESSION}",
            f"{OCI_VERSION_LABEL}=edge",
        ),
        (
            f"{OCI_REVISION_LABEL}={REVISION_EXPRESSION}",
            f"{OCI_REVISION_LABEL}=9065270",
        ),
        (
            f"REVISION={REVISION_EXPRESSION}",
            "REVISION=9065270",
        ),
        (
            f"{OCI_SOURCE_LABEL}={SOURCE_EXPRESSION}",
            f"{OCI_SOURCE_LABEL}=https://github.com/example/fork",
        ),
        (
            f"labels: {VALIDATED_LABELS_EXPRESSION}",
            "labels: ${{ steps.meta.outputs.labels }}",
        ),
        (
            f"DOCKER_METADATA_OUTPUT_JSON: {METADATA_JSON_EXPRESSION}",
            "DOCKER_METADATA_OUTPUT_JSON: '{}'",
        ),
        (
            "run: python3 deploy/docker/validate_oci_metadata.py",
            "run: echo metadata accepted",
        ),
        (
            "type=sha,prefix=sha-,format=short",
            "type=sha,prefix=sha-,format=long",
        ),
        (
            "apps/core/tests/contracts/test_docker_metadata_contract.py",
            "apps/core/tests/test_docker_deploy.py",
        ),
    ),
)
def test_docker_workflow_contract_rejects_identity_weakening(
    old: str,
    new: str,
) -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert old in workflow
    with pytest.raises(AssertionError):
        _assert_workflow_contract(workflow.replace(old, new, 1))


def test_docker_workflow_contract_rejects_metadata_before_version() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    version_step = _step_body(workflow, "Read package version")
    metadata_step = _step_body(workflow, "Docker metadata")
    weakened = workflow.replace(version_step, "", 1)
    weakened = weakened.replace(
        metadata_step,
        metadata_step + "\n" + version_step,
        1,
    )
    with pytest.raises(AssertionError):
        _assert_workflow_contract(weakened)


def test_docker_workflow_contract_rejects_soft_failed_validation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    validate = _step_body(workflow, "Validate Docker metadata labels")
    weakened = validate.replace(
        "id: validated-metadata",
        "id: validated-metadata\n        continue-on-error: true",
        1,
    )
    with pytest.raises(AssertionError):
        _assert_workflow_contract(workflow.replace(validate, weakened, 1))


def test_canonical_local_build_resolves_full_git_head(tmp_path: Path) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode == 0, result.stderr
    assert re.fullmatch(r"[0-9a-f]{40}", revision)
    assert _recorded_docker_arguments(docker_args) == (
        _expected_local_build_arguments(revision)
    )


def test_canonical_local_build_honours_revision_override_without_git(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = "a" * 40

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"ZIGBEELENS_REVISION": revision},
    )

    assert result.returncode == 0, result.stderr
    assert _recorded_docker_arguments(docker_args) == (
        _expected_local_build_arguments(revision)
    )


def test_canonical_local_build_fails_without_git_or_override(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode != 0
    assert "unable to resolve a Git revision" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_rejects_unrelated_parent_git_checkout(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    _git(parent, "init", "--quiet")
    (parent / "parent-marker").write_text("unrelated\n", encoding="utf-8")
    _git(parent, "add", "parent-marker")
    _git(
        parent,
        "-c",
        "user.name=ZigbeeLens contract",
        "-c",
        "user.email=contracts@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "unrelated parent",
    )
    checkout, fake_bin, docker_args = _local_build_fixture(parent)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode != 0
    assert "build root must be the exact Git checkout root" in result.stderr
    assert not docker_args.exists()


@pytest.mark.parametrize(
    "revision",
    (
        "",
        "9065270",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "g" * 40,
        f" {'a' * 40}",
        f"{'a' * 40} ",
        f"{'a' * 20}\n{'a' * 20}",
    ),
    ids=(
        "empty",
        "abbreviated",
        "39-characters",
        "41-characters",
        "uppercase",
        "non-hex",
        "leading-whitespace",
        "trailing-whitespace",
        "embedded-newline",
    ),
)
def test_canonical_local_build_rejects_invalid_explicit_revision_before_docker(
    tmp_path: Path,
    revision: str,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"ZIGBEELENS_REVISION": revision},
    )

    assert result.returncode != 0
    assert "full 40-character lowercase hexadecimal Git SHA" in result.stderr
    assert not docker_args.exists()


@pytest.mark.parametrize(
    "resolved_revision",
    (
        "9065270",
        "A" * 40,
        "g" * 40,
        "a" * 39,
        "a" * 41,
    ),
)
def test_canonical_local_build_rejects_invalid_git_resolution_before_docker(
    tmp_path: Path,
    resolved_revision: str,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == \"rev-parse --show-toplevel\" ]]; then\n"
        '  printf "%s\\n" "${FAKE_GIT_TOPLEVEL:?}"\n'
        "else\n"
        f"  printf '%s\\n' '{resolved_revision}'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"FAKE_GIT_TOPLEVEL": str(checkout)},
    )

    assert result.returncode != 0
    assert "full 40-character lowercase hexadecimal Git SHA" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_rejects_failed_git_with_plausible_stdout(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == \"rev-parse --show-toplevel\" ]]; then\n"
        '  printf "%s\\n" "${FAKE_GIT_TOPLEVEL:?}"\n'
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' '{'a' * 40}'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"FAKE_GIT_TOPLEVEL": str(checkout)},
    )

    assert result.returncode != 0
    assert "unable to resolve a Git revision" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_resolves_detached_head(tmp_path: Path) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    _git(checkout, "checkout", "--quiet", "--detach", revision)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode == 0, result.stderr
    assert _git(checkout, "branch", "--show-current") == ""
    assert _recorded_docker_arguments(docker_args) == (
        _expected_local_build_arguments(revision)
    )


def test_canonical_local_build_deliberately_identifies_head_when_dirty(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    fixture_dockerfile = checkout / "deploy" / "docker" / "Dockerfile"
    fixture_dockerfile.write_text(
        fixture_dockerfile.read_text(encoding="utf-8") + "\n# dirty fixture\n",
        encoding="utf-8",
    )
    assert _git(checkout, "status", "--short")

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode == 0, result.stderr
    assert _recorded_docker_arguments(docker_args) == (
        _expected_local_build_arguments(revision)
    )


@pytest.mark.parametrize(
    ("package_version", "version_override"),
    (
        (PACKAGE_VERSION, ""),
        (PACKAGE_VERSION, "edge"),
        (PACKAGE_VERSION, "0.1.15"),
        ("edge", None),
        ("01.2.3", None),
    ),
    ids=(
        "empty-override",
        "channel-override",
        "misaligned-semver-override",
        "package-channel",
        "non-strict-package-semver",
    ),
)
def test_canonical_local_build_rejects_invalid_or_misaligned_version_before_docker(
    tmp_path: Path,
    package_version: str,
    version_override: str | None,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(
        tmp_path,
        package_version=package_version,
    )
    environment = {"ZIGBEELENS_REVISION": "a" * 40}
    if version_override is not None:
        environment["ZIGBEELENS_VERSION"] = version_override

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment=environment,
    )

    assert result.returncode != 0
    assert "version" in result.stderr.lower()
    assert not docker_args.exists()


def test_canonical_local_build_accepts_exact_package_version_override(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = "b" * 40

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={
            "ZIGBEELENS_REVISION": revision,
            "ZIGBEELENS_VERSION": PACKAGE_VERSION,
        },
    )

    assert result.returncode == 0, result.stderr
    assert _recorded_docker_arguments(docker_args) == (
        _expected_local_build_arguments(revision)
    )


def test_dockerfile_owns_version_revision_and_source_labels() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    first_from = dockerfile.index("FROM ")
    runtime_start = dockerfile.index("FROM python:3.12-slim AS runtime")
    before_runtime = dockerfile[:runtime_start]
    runtime = dockerfile[runtime_start:]

    assert dockerfile[:first_from].count("ARG VERSION=0.1.14") == 1
    assert dockerfile[:first_from].count("ARG REVISION") == 1
    assert dockerfile[:first_from].count(f"ARG IMAGE_SOURCE={IMAGE_SOURCE}") == 1
    assert runtime.count("\nARG VERSION\n") == 1
    assert runtime.count("\nARG REVISION\n") == 1
    assert runtime.count("\nARG IMAGE_SOURCE\n") == 1
    assert runtime.count(
        'org.opencontainers.image.version="${VERSION}"'
    ) == 1
    assert runtime.count(
        'org.opencontainers.image.revision="${REVISION}"'
    ) == 1
    assert runtime.count(
        'org.opencontainers.image.source="${IMAGE_SOURCE}"'
    ) == 1
    assert "org.opencontainers.image.version=" not in before_runtime
    assert "org.opencontainers.image.revision=" not in before_runtime
    assert "org.opencontainers.image.source=" not in before_runtime


def test_ci_no_push_build_passes_exact_checkout_identity() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    build = _step_body(workflow, "Build Docker image (no push)")

    assert build.count(f"VERSION={VERSION_EXPRESSION}") == 1
    assert build.count(f"REVISION={REVISION_EXPRESSION}") == 1
    assert build.count(f"IMAGE_SOURCE={SOURCE_EXPRESSION}") == 1


def test_docker_smoke_uses_canonical_local_build_owner() -> None:
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")

    assert smoke.count(
        'ZIGBEELENS_IMAGE="${IMAGE}" "${ROOT}/scripts/build-docker.sh"'
    ) == 1
    assert "docker build" not in smoke


def test_validated_labels_preserve_metadata_after_identity_check() -> None:
    labels = validated_labels_from_json(
        json.dumps(_metadata_payload()),
        expected_version=PACKAGE_VERSION,
        expected_revision=FULL_REVISION,
        expected_source=IMAGE_SOURCE,
    )
    assert labels == tuple(sorted(labels))
    assert f"{OCI_VERSION_LABEL}={PACKAGE_VERSION}" in labels
    assert f"{OCI_REVISION_LABEL}={FULL_REVISION}" in labels
    assert f"{OCI_SOURCE_LABEL}={IMAGE_SOURCE}" in labels
    assert ("org.opencontainers.image.description=Read-only observability console") in labels


@pytest.mark.parametrize("channel", ("edge", "main", "latest"))
def test_metadata_validator_rejects_channel_as_version(
    channel: str,
) -> None:
    payload = _metadata_payload()
    payload["labels"][OCI_VERSION_LABEL] = channel
    with pytest.raises(MetadataValidationError):
        validated_labels_from_json(
            json.dumps(payload),
            expected_version=PACKAGE_VERSION,
            expected_revision=FULL_REVISION,
            expected_source=IMAGE_SOURCE,
        )


@pytest.mark.parametrize(
    ("label", "replacement"),
    (
        (OCI_VERSION_LABEL, ""),
        (OCI_REVISION_LABEL, "9065270"),
        (OCI_REVISION_LABEL, ""),
        (OCI_SOURCE_LABEL, "https://github.com/example/fork"),
        (OCI_SOURCE_LABEL, ""),
    ),
)
def test_metadata_validator_rejects_wrong_or_missing_identity(
    label: str,
    replacement: str,
) -> None:
    payload = _metadata_payload()
    if replacement:
        payload["labels"][label] = replacement
    else:
        del payload["labels"][label]
    with pytest.raises(MetadataValidationError):
        validated_labels_from_json(
            json.dumps(payload),
            expected_version=PACKAGE_VERSION,
            expected_revision=FULL_REVISION,
            expected_source=IMAGE_SOURCE,
        )


@pytest.mark.parametrize(
    ("version", "revision", "source"),
    (
        ("edge", FULL_REVISION, IMAGE_SOURCE),
        (PACKAGE_VERSION, "9065270", IMAGE_SOURCE),
        (PACKAGE_VERSION, FULL_REVISION, ""),
    ),
)
def test_metadata_validator_rejects_invalid_expected_identity(
    version: str,
    revision: str,
    source: str,
) -> None:
    with pytest.raises(MetadataValidationError):
        validated_labels_from_json(
            json.dumps(_metadata_payload()),
            expected_version=version,
            expected_revision=revision,
            expected_source=source,
        )


def test_metadata_validator_rejects_duplicate_label_keys() -> None:
    metadata_json = (
        '{"tags":["ghcr.io/theaussiepom/zigbeelens:edge"],'
        '"labels":{'
        f'"{OCI_VERSION_LABEL}":"{PACKAGE_VERSION}",'
        f'"{OCI_VERSION_LABEL}":"edge",'
        f'"{OCI_REVISION_LABEL}":"{FULL_REVISION}",'
        f'"{OCI_SOURCE_LABEL}":"{IMAGE_SOURCE}"'
        "}}"
    )
    with pytest.raises(MetadataValidationError):
        validated_labels_from_json(
            metadata_json,
            expected_version=PACKAGE_VERSION,
            expected_revision=FULL_REVISION,
            expected_source=IMAGE_SOURCE,
        )


def test_validator_cli_exports_only_validated_labels(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        {
            "DOCKER_METADATA_OUTPUT_JSON": json.dumps(_metadata_payload()),
            "EXPECTED_OCI_VERSION": PACKAGE_VERSION,
            "EXPECTED_OCI_REVISION": FULL_REVISION,
            "EXPECTED_OCI_SOURCE": IMAGE_SOURCE,
            "GITHUB_OUTPUT": str(github_output),
        }
    )
    result = subprocess.run(
        [sys.executable, VALIDATOR],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    output = github_output.read_text(encoding="utf-8")
    assert output.startswith("labels<<ZIGBEELENS_VALIDATED_OCI_LABELS\n")
    assert f"{OCI_VERSION_LABEL}={PACKAGE_VERSION}\n" in output
    assert f"{OCI_REVISION_LABEL}={FULL_REVISION}\n" in output
    assert f"{OCI_SOURCE_LABEL}={IMAGE_SOURCE}\n" in output


def test_validator_cli_fails_without_full_revision(
    tmp_path: Path,
) -> None:
    payload = _metadata_payload()
    payload["labels"][OCI_REVISION_LABEL] = "9065270"
    github_output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        {
            "DOCKER_METADATA_OUTPUT_JSON": json.dumps(payload),
            "EXPECTED_OCI_VERSION": PACKAGE_VERSION,
            "EXPECTED_OCI_REVISION": FULL_REVISION,
            "EXPECTED_OCI_SOURCE": IMAGE_SOURCE,
            "GITHUB_OUTPUT": str(github_output),
        }
    )
    result = subprocess.run(
        [sys.executable, VALIDATOR],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not github_output.exists()
