"""Regression tests for staged HACS package source provenance."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PACKAGER = ROOT / "scripts" / "package-hacs-repo.sh"
README_TEMPLATE = ROOT / "release" / "zigbeelens-hacs" / "README.md.in"
PACKAGE_VALIDATOR = (
    ROOT / "release" / "zigbeelens-hacs" / "scripts" / "validate-hacs-repo.sh"
)
INTEGRATION_SOURCE = ROOT / "apps" / "ha_integration" / "custom_components" / "zigbeelens"
WORKFLOW_SOURCE = ROOT / "release" / "zigbeelens-hacs" / ".github" / "workflows"


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _fixture_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    _copy_file(PACKAGER, repository / "scripts" / "package-hacs-repo.sh")
    _copy_file(
        README_TEMPLATE,
        repository / "release" / "zigbeelens-hacs" / "README.md.in",
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
    shutil.copytree(
        INTEGRATION_SOURCE,
        repository / "apps" / "ha_integration" / "custom_components" / "zigbeelens",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=ZigbeeLens Tests",
            "-c",
            "user.email=tests@zigbeelens.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    return repository


def _run_packager(
    repository: Path, *, source_commit: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("ZIGBEELENS_SOURCE_COMMIT", None)
    if source_commit is not None:
        env["ZIGBEELENS_SOURCE_COMMIT"] = source_commit
    return subprocess.run(
        ["bash", "scripts/package-hacs-repo.sh"],
        cwd=repository,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def _assert_packaged_provenance(repository: Path, expected_commit: str) -> None:
    stage = repository / "dist" / "zigbeelens-hacs"
    assert (stage / "SOURCE_COMMIT").read_bytes() == (
        f"{expected_commit}\n".encode()
    )
    manifest = json.loads(
        (
            stage / "custom_components" / "zigbeelens" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    documentation = (
        "https://github.com/theaussiepom/zigbeelens/blob/"
        f"{expected_commit}/docs/hacs.md"
    )
    assert manifest["documentation"] == documentation

    readme = (stage / "README.md").read_text(encoding="utf-8")
    local_section = readme.split("## Local staged integration testing", 1)[1].split(
        "## Conditional public HACS installation", 1
    )[0]
    expected_commit_link = (
        f"[`{expected_commit}`](https://github.com/theaussiepom/zigbeelens/"
        f"commit/{expected_commit})"
    )
    assert local_section.count(expected_commit_link) == 1
    assert local_section.count(documentation) == 1
    assert "@SOURCE_COMMIT@" not in readme


def _run_package_validator(repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "scripts/validate-hacs-repo.sh"],
        cwd=repository / "dist" / "zigbeelens-hacs",
        check=False,
        capture_output=True,
        text=True,
    )


def test_packager_derives_source_commit_from_git_head(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = _run_packager(repository)

    assert result.returncode == 0, result.stderr
    _assert_packaged_provenance(repository, head)


def test_packager_normalizes_source_commit_override(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    override = "A1" * 20

    result = _run_packager(repository, source_commit=override)

    assert result.returncode == 0, result.stderr
    _assert_packaged_provenance(repository, override.lower())


def test_package_validator_accepts_matching_provenance(tmp_path: Path):
    repository = _fixture_repository(tmp_path)
    source_commit = "b" * 40
    package_result = _run_packager(repository, source_commit=source_commit)
    assert package_result.returncode == 0, package_result.stderr

    validation = _run_package_validator(repository)

    assert validation.returncode == 0, validation.stderr
    assert (
        "OK: SOURCE_COMMIT agrees with README and pinned manifest documentation"
        in validation.stdout
    )


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
    tmp_path: Path, invalid: str
):
    repository = _fixture_repository(tmp_path)

    result = _run_packager(repository, source_commit=invalid)

    assert result.returncode == 1
    assert (
        "ZIGBEELENS_SOURCE_COMMIT must be exactly 40 hexadecimal characters"
        in result.stderr
    )


@pytest.mark.parametrize("mismatch_surface", ("manifest", "readme", "source_file"))
def test_package_validator_rejects_source_commit_mismatch(
    tmp_path: Path, mismatch_surface: str
):
    repository = _fixture_repository(tmp_path)
    source_commit = "b" * 40
    mismatched_commit = "c" * 40
    package_result = _run_packager(repository, source_commit=source_commit)
    assert package_result.returncode == 0, package_result.stderr

    stage = repository / "dist" / "zigbeelens-hacs"
    if mismatch_surface == "manifest":
        manifest_path = (
            stage / "custom_components" / "zigbeelens" / "manifest.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["documentation"] = manifest["documentation"].replace(
            source_commit, mismatched_commit
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    elif mismatch_surface == "readme":
        readme_path = stage / "README.md"
        readme = readme_path.read_text(encoding="utf-8").replace(
            source_commit, mismatched_commit
        )
        readme += (
            "\nDecoy package provenance outside the local-stage section:\n"
            f"[`{source_commit}`](https://github.com/theaussiepom/zigbeelens/"
            f"commit/{source_commit})\n"
            "https://github.com/theaussiepom/zigbeelens/blob/"
            f"{source_commit}/docs/hacs.md\n"
        )
        readme_path.write_text(readme, encoding="utf-8")
    else:
        (stage / "SOURCE_COMMIT").write_text(
            f"{mismatched_commit}\n", encoding="utf-8"
        )

    validation = _run_package_validator(repository)

    assert validation.returncode != 0
    assert "SOURCE_COMMIT" in f"{validation.stdout}\n{validation.stderr}"
