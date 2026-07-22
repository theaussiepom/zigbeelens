"""Exercise the real validate-contracts.sh Python resolver (no suite run)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "validate-contracts.sh"


def _base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "CORE_PYTHON"}


def _make_executable(path: Path, marker: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho {marker}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _isolated_bin(tmp_path: Path, *executables: Path) -> Path:
    """PATH containing only bash plus the provided controlled executables."""
    bin_dir = tmp_path / "isolated-bin"
    bin_dir.mkdir()
    bash = shutil.which("bash")
    assert bash, "bash is required to exercise validate-contracts.sh"
    (bin_dir / "bash").symlink_to(bash)
    for src in executables:
        dest = bin_dir / src.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(src.resolve())
    return bin_dir


def _print_core_python(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    path_entries = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    bash_path = Path(path_entries[0]) / "bash" if path_entries else Path("bash")
    return subprocess.run(
        [str(bash_path), str(SCRIPT), "--print-core-python"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _fake_repo_with_venv(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "fake-repo"
    venv_python = _make_executable(
        root / "apps" / "core" / ".venv" / "bin" / "python",
        "venv",
    )
    return root, venv_python


def test_validate_contracts_script_explicit_core_python_wins(tmp_path: Path):
    fake_root, venv_python = _fake_repo_with_venv(tmp_path)
    python3 = _make_executable(tmp_path / "python3", "python3")
    python = _make_executable(tmp_path / "python", "python")
    explicit = _make_executable(tmp_path / "explicit-python", "explicit")
    bin_dir = _isolated_bin(tmp_path, python3, python)
    env = _base_env()
    env["CORE_PYTHON"] = str(explicit)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    env["PATH"] = str(bin_dir)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(explicit)
    assert "Core contract suite" not in result.stdout
    assert "UI contract suite" not in result.stdout
    assert venv_python.exists()


def test_validate_contracts_script_prefers_temp_venv_over_path_pythons(tmp_path: Path):
    fake_root, venv_python = _fake_repo_with_venv(tmp_path)
    python3 = _make_executable(tmp_path / "python3", "python3")
    python = _make_executable(tmp_path / "python", "python")
    bin_dir = _isolated_bin(tmp_path, python3, python)
    env = _base_env()
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    env["PATH"] = str(bin_dir)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == venv_python.resolve()


def test_validate_contracts_script_falls_back_to_python3(tmp_path: Path):
    fake_root = tmp_path / "repo-no-venv"
    fake_root.mkdir()
    python3 = _make_executable(tmp_path / "python3", "python3")
    python = _make_executable(tmp_path / "python", "python")
    bin_dir = _isolated_bin(tmp_path, python3, python)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (bin_dir / "python3").resolve()


def test_validate_contracts_script_falls_back_to_python(tmp_path: Path):
    fake_root = tmp_path / "repo-no-venv"
    fake_root.mkdir()
    python = _make_executable(tmp_path / "python", "python")
    bin_dir = _isolated_bin(tmp_path, python)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (bin_dir / "python").resolve()


def test_validate_contracts_script_fails_without_interpreter(tmp_path: Path):
    fake_root = tmp_path / "repo-no-venv"
    fake_root.mkdir()
    bin_dir = _isolated_bin(tmp_path)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode != 0
    assert "no Python interpreter found" in result.stderr
    assert "Core contract suite" not in result.stdout
    assert "UI contract suite" not in result.stdout


def test_validate_contracts_script_mentions_no_uv_requirement():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "uv run" not in text
    assert "CORE_PYTHON" in text
    assert "-m pytest" in text
    assert "--print-core-python" in text
    assert "BASH_SOURCE[0]" in text
    assert "dirname " not in text
    assert 'dirname "' not in text
    assert "$(dirname" not in text
    assert "${SCRIPT_PATH%/*}" in text
