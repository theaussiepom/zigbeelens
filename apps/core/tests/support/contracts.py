"""Shared helpers for Core contract tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
ORACLE_GENERATOR = REPO_ROOT / "apps" / "core" / "scripts" / "generate_oracle_mock_fixtures.py"
ORACLE_FIXTURE = (
    REPO_ROOT / "apps" / "ui" / "src" / "test" / "fixtures" / "oracleMockScenarios.json"
)


def load_oracle_fixture() -> dict:
    return json.loads(ORACLE_FIXTURE.read_text(encoding="utf-8"))


def generate_oracle_fixture_text(
    *,
    output: Path | None = None,
    check: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(ORACLE_GENERATOR)]
    if check:
        cmd.append("--check")
    if output is not None:
        cmd.extend(["--output", str(output)])
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def oracle_scenarios(payload: dict | None = None) -> dict[str, dict]:
    body = payload if payload is not None else load_oracle_fixture()
    scenarios = body.get("scenarios")
    if not isinstance(scenarios, dict):
        raise AssertionError("oracle fixture missing scenarios object")
    return scenarios
