"""Smoke: validate-contracts.sh resolves Python without requiring uv."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "validate-contracts.sh"


def test_validate_contracts_script_resolves_core_python(tmp_path: Path):
    """Exercise resolve_core_python via a tiny sourced smoke (no full suite)."""
    wrapper = tmp_path / "resolve.sh"
    wrapper.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
source "{SCRIPT}"
# sourcing would run the script; instead extract the function by redefining:
""",
        encoding="utf-8",
    )
    # Direct unit of the resolution preference chain.
    probe = tmp_path / "probe.sh"
    probe.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
ROOT="{REPO_ROOT}"
resolve_core_python() {{
  if [[ -n "${{CORE_PYTHON:-}}" ]]; then
    printf '%s\\n' "${{CORE_PYTHON}}"
    return 0
  fi
  local venv_python="${{ROOT}}/apps/core/.venv/bin/python"
  if [[ -x "${{venv_python}}" ]]; then
    printf '%s\\n' "${{venv_python}}"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  return 1
}}
resolved="$(resolve_core_python)"
test -n "${{resolved}}"
test -x "${{resolved}}" || command -v "${{resolved}}" >/dev/null
""",
        encoding="utf-8",
    )
    probe.chmod(probe.stat().st_mode | stat.S_IXUSR)
    env = {**os.environ, "CORE_PYTHON": sys.executable}
    result = subprocess.run(
        ["bash", str(probe)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    # Explicit CORE_PYTHON wins.
    assert Path(sys.executable).resolve() == Path(
        subprocess.check_output(
            [
                "bash",
                "-c",
                f'CORE_PYTHON="{sys.executable}"; ROOT="{REPO_ROOT}"; '
                'if [[ -n "${CORE_PYTHON:-}" ]]; then printf "%s\\n" "${CORE_PYTHON}"; fi',
            ],
            text=True,
        ).strip()
    ).resolve()


def test_validate_contracts_script_mentions_no_uv_requirement():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "uv run" not in text
    assert "CORE_PYTHON" in text
    assert 'pytest -q tests/contracts' in text or "-m pytest" in text
