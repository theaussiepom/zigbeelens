"""Fail-closed contracts for release identity in Docker image metadata."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
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
