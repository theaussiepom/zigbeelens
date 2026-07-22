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


def _isolated_bin(tmp_path: Path, *names: Path) -> Path:
    """PATH with only controlled executables (plus bash for the script itself)."""
    bin_dir = tmp_path / "isolated-bin"
    bin_dir.mkdir()
    bash = shutil.which("bash")
    assert bash, "bash is required to exercise validate-contracts.sh"
    (bin_dir / "bash").symlink_to(bash)
    for src in names:
        dest = bin_dir / src.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(src)
    return bin_dir


def _print_core_python(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bash = env.get("PATH", "").split(os.pathsep)[0]
    bash_path = Path(bash) / "bash" if bash else Path(shutil.which("bash") or "bash")
    return subprocess.run(
        [str(bash_path) if bash_path.exists() else "bash", str(SCRIPT), "--print-core-python"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_validate_contracts_script_explicit_core_python(tmp_path: Path):
    fake = tmp_path / "explicit-python"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    bin_dir = _isolated_bin(tmp_path)
    env = _base_env()
    env["CORE_PYTHON"] = str(fake)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(tmp_path)
    env["PATH"] = str(bin_dir)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(fake)


def test_validate_contracts_script_prefers_core_venv(tmp_path: Path):
    bin_dir = _isolated_bin(tmp_path)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(REPO_ROOT)
    result = _print_core_python(env)
    venv_python = REPO_ROOT / "apps" / "core" / ".venv" / "bin" / "python"
    if venv_python.is_file() and os.access(venv_python, os.X_OK):
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()).resolve() == venv_python.resolve()
    else:
        assert result.returncode != 0
        assert "no Python interpreter found" in result.stderr


def test_validate_contracts_script_falls_back_to_python3(tmp_path: Path):
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    python3 = tmp_path / "python3"
    python3.write_text("#!/bin/sh\n", encoding="utf-8")
    python3.chmod(python3.stat().st_mode | stat.S_IXUSR)
    bin_dir = _isolated_bin(tmp_path, python3)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (bin_dir / "python3").resolve()


def test_validate_contracts_script_falls_back_to_python(tmp_path: Path):
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    bin_dir = _isolated_bin(tmp_path, python)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == (bin_dir / "python").resolve()


def test_validate_contracts_script_fails_without_interpreter(tmp_path: Path):
    fake_root = tmp_path / "repo"
    fake_root.mkdir()
    bin_dir = _isolated_bin(tmp_path)
    env = _base_env()
    env["PATH"] = str(bin_dir)
    env["ZIGBEELENS_CONTRACT_ROOT"] = str(fake_root)
    result = _print_core_python(env)
    assert result.returncode != 0
    assert "no Python interpreter found" in result.stderr


def test_validate_contracts_script_mentions_no_uv_requirement():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "uv run" not in text
    assert "CORE_PYTHON" in text
    assert "-m pytest" in text
    assert "--print-core-python" in text
    assert "BASH_SOURCE[0]" in text
