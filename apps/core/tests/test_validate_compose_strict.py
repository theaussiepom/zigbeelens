"""Regression tests for fail-closed Compose release validation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "scripts" / "validate-compose.sh"


def _failing_docker_path(tmp_path: Path) -> str:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "compose" ] && [ "$2" = "version" ]; then\n'
        "  exit 41\n"
        "fi\n"
        'echo "unexpected fake docker invocation: $*" >&2\n'
        "exit 99\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"


def _run_validator(tmp_path: Path, *, strict: bool) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = _failing_docker_path(tmp_path)
    if strict:
        env["ZIGBEELENS_REQUIRE_DOCKER_COMPOSE"] = "1"
    else:
        env.pop("ZIGBEELENS_REQUIRE_DOCKER_COMPOSE", None)
    return subprocess.run(
        ["bash", str(VALIDATOR)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_strict_compose_validation_fails_when_version_probe_fails(tmp_path: Path):
    result = _run_validator(tmp_path, strict=True)

    assert result.returncode == 1
    assert (
        "FAIL: Docker Compose rendering is required: "
        "docker compose version check failed"
    ) in result.stderr
    assert "Docker/Compose validation passed." not in result.stdout


def test_non_strict_compose_validation_reports_partial_result(tmp_path: Path):
    result = _run_validator(tmp_path, strict=False)

    assert result.returncode == 0
    assert "SKIP: Docker Compose rendering not run" in result.stdout
    assert (
        "Docker/Compose source checks passed; rendering not run." in result.stdout
    )
    assert "Docker/Compose validation passed." not in result.stdout
