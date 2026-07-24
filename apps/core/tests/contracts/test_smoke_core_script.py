"""Hermetic ownership contract for the canonical Core smoke gate."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[4]
SMOKE = ROOT / "scripts" / "smoke-core.sh"
RELEASE_HELPER = ROOT / "scripts" / "run-release-checks.sh"
ADDON_VALIDATOR = ROOT / "scripts" / "validate-addon.sh"
STATE_GLOB = "zigbeelens-core-smoke.*"


def _fixture_repository(
    tmp_path: Path,
    *,
    package_version: str | None = None,
    version_api_override: str | None = None,
) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    script = repository / "scripts" / "smoke-core.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(SMOKE, script)

    core = repository / "apps" / "core"
    core.mkdir(parents=True)
    source_root = ROOT / "apps" / "core" / "src"
    shutil.copytree(
        source_root,
        core / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for project_file in ("pyproject.toml", "README.md"):
        shutil.copy2(ROOT / "apps" / "core" / project_file, core / project_file)

    if package_version is not None:
        pyproject = core / "pyproject.toml"
        updated, replacements = re.subn(
            r'(?m)^version = "[^"]+"$',
            f'version = "{package_version}"',
            pyproject.read_text(encoding="utf-8"),
        )
        assert replacements == 1
        pyproject.write_text(updated, encoding="utf-8")

        package_init = core / "src" / "zigbeelens" / "__init__.py"
        updated, replacements = re.subn(
            r'(?m)^__version__ = "[^"]+"$',
            f'__version__ = "{package_version}"',
            package_init.read_text(encoding="utf-8"),
        )
        assert replacements == 1
        package_init.write_text(updated, encoding="utf-8")

    if version_api_override is not None:
        routes = core / "src" / "zigbeelens" / "api" / "routes.py"
        original = 'return {"version": __version__, "name": "zigbeelens-core"}'
        replacement = (
            f'return {{"version": "{version_api_override}", '
            '"name": "zigbeelens-core"}'
        )
        text = routes.read_text(encoding="utf-8")
        assert text.count(original) == 1
        routes.write_text(text.replace(original, replacement, 1), encoding="utf-8")

    assert not (core / "uv.lock").exists()
    config_sentinel = repository / "config" / "config.yaml"
    config_sentinel.parent.mkdir()
    config_sentinel.write_bytes(b"production-config-sentinel\n")
    data_sentinel = repository / "data" / "zigbeelens.sqlite"
    data_sentinel.parent.mkdir()
    data_sentinel.write_bytes(b"production-data-sentinel\n")
    return repository, script


def _environment(
    tmp_path: Path,
    *,
    python: str | None = sys.executable,
) -> tuple[dict[str, str], Path]:
    tmp_parent = tmp_path / "temporary-state"
    tmp_parent.mkdir(exist_ok=True)
    env = os.environ.copy()
    for name in (
        "SMOKE_PORT",
        "ZIGBEELENS_CONFIG",
        "ZIGBEELENS_PORT",
        "ZIGBEELENS_CORE_PYTHON",
    ):
        env.pop(name, None)
    env["TMPDIR"] = str(tmp_parent)
    if python is not None:
        env["ZIGBEELENS_CORE_PYTHON"] = python
    return env, tmp_parent


def _lock_snapshot(script: Path) -> dict[Path, bytes | None]:
    paths = (
        script.parents[1] / "apps" / "core" / "uv.lock",
        ROOT / "apps" / "core" / "uv.lock",
    )
    return {
        path: path.read_bytes() if path.is_file() else None
        for path in paths
    }


def _assert_locks_unchanged(snapshot: dict[Path, bytes | None]) -> None:
    for path, before in snapshot.items():
        if before is None:
            assert not path.exists(), f"smoke created ignored lockfile: {path}"
        else:
            assert path.read_bytes() == before, f"smoke modified ignored lockfile: {path}"


def _run(
    script: Path,
    *,
    env: dict[str, str],
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    locks_before = _lock_snapshot(script)
    try:
        return subprocess.run(
            ["/bin/bash", str(script)],
            cwd=script.parents[1],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        _assert_locks_unchanged(locks_before)


def _tracked_files_repository(tmp_path: Path) -> Path:
    """Export the current Git-tracked file set without ignored local state."""
    repository = tmp_path / "tracked-repository"
    repository.mkdir()
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    for raw_relative in tracked.split(b"\0"):
        if not raw_relative:
            continue
        relative = Path(os.fsdecode(raw_relative))
        source = ROOT / relative
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            destination.symlink_to(os.readlink(source))
        else:
            shutil.copy2(source, destination)

    assert not (repository / ".git").exists()
    assert not (repository / "apps" / "core" / "uv.lock").exists()
    assert not (repository / "apps" / "core" / ".venv").exists()
    assert not (repository / "data").exists()
    return repository


def _assert_no_state(tmp_parent: Path) -> None:
    assert list(tmp_parent.glob(STATE_GLOB)) == []


def _write_python_wrapper(
    path: Path,
    *,
    server: str = "delegate",
    marker: Path | None = None,
    child_pid: Path | None = None,
) -> None:
    marker_line = (
        f'printf "%s\\n" "$*" >> {shlex_quote(str(marker))}\n'
        if marker is not None
        else ""
    )
    if server == "exit":
        server_lines = (
            'case "${2:-}" in\n'
            "  */core.pid)\n"
            '  echo "forced safe startup failure" >&2\n'
            "  exit 23\n"
            "  ;;\n"
            "esac\n"
        )
    else:
        server_lines = ""
    path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"{marker_line}"
        f"{server_lines}"
        f"exec {shlex_quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)

    if server == "ignore-term":
        assert child_pid is not None
        path.write_text(
            f"#!{sys.executable}\n"
            "import os\n"
            "from pathlib import Path\n"
            "import signal\n"
            "import sys\n"
            "import time\n"
            f"real_python = {sys.executable!r}\n"
            "if len(sys.argv) > 2 and Path(sys.argv[2]).name == 'core.pid':\n"
            "    Path(sys.argv[2]).write_text(f'{os.getpid()}\\n', encoding='utf-8')\n"
            f"    Path({str(child_pid)!r}).write_text(str(os.getpid()), encoding='utf-8')\n"
            "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "    while True:\n"
            "        time.sleep(1)\n"
            "os.execv(real_python, [real_python, *sys.argv[1:]])\n",
            encoding="utf-8",
        )
        path.chmod(0o755)


def shlex_quote(value: str) -> str:
    """Return a shell-safe single argument without importing a shell runner."""
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _write_uv_process_runner(path: Path, child_pid: Path) -> None:
    term_ignoring_child = path.parent / "term-ignoring-uv-child.py"
    term_ignoring_child.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import signal\n"
        "import sys\n"
        "import time\n"
        "Path(sys.argv[1]).write_text(f'{os.getpid()}\\n', encoding='utf-8')\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "Path(sys.argv[2]).write_text(str(os.getpid()), encoding='utf-8')\n"
        "while True:\n"
        "    time.sleep(1)\n",
        encoding="utf-8",
    )
    path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'while [ "$#" -gt 0 ] && [ "$1" != "python" ]; do\n'
        "  shift\n"
        "done\n"
        '[ "$#" -gt 0 ] || exit 64\n'
        "shift\n"
        'case "${2:-}" in\n'
        "  */core.pid)\n"
        f"    {shlex_quote(sys.executable)} "
        f"{shlex_quote(str(term_ignoring_child))} "
        f'"$2" {shlex_quote(str(child_pid))} <&0 &\n'
        "    ;;\n"
        "  *)\n"
        f"    {shlex_quote(sys.executable)} \"$@\" <&0 &\n"
        "    ;;\n"
        "esac\n"
        "runner_child=$!\n"
        'wait "$runner_child"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_smoke_script_is_hermetic_and_release_owned() -> None:
    text = SMOKE.read_text(encoding="utf-8")
    helper = RELEASE_HELPER.read_text(encoding="utf-8")
    addon_validator = ADDON_VALIDATOR.read_text(encoding="utf-8")

    assert "apps/core/.venv" not in text
    assert "source " not in text
    assert "pip install" not in text
    assert "config/config.yaml" not in text
    assert "./data/" not in text
    assert '"$UV_COMMAND" run' in text
    assert "--isolated" in text
    assert "--locked" not in text
    assert "--no-project" in text
    assert "--no-config" in text
    assert "--no-env-file" in text
    assert "\n    --project " not in text
    assert "--extra dev" not in text
    assert '--with-editable "$ROOT/apps/core[dev]"' in text
    assert "zigbeelens.__version__" in text
    assert "EXPECTED_VERSION" in text
    canonical_version = re.search(
        r'(?m)^version = "([^"]+)"$',
        (ROOT / "apps" / "core" / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert canonical_version is not None
    assert canonical_version.group(1) not in text
    assert "mktemp -d" in text
    assert "mqtt_attempts=0" in text
    assert 'CORE_PID_PATH="$STATE_DIR/core.pid"' in text
    assert "CORE_RUNNER_PID" in text
    assert '"mqtt_collector": False' in text
    assert '"mqtt_discovery": False' in text
    assert '"enabled": False' in text
    assert '"startup_scan": False' in text
    assert '"manual_capture_enabled": False' in text
    assert '"automatic_capture_enabled": False' in text
    assert '"schema_version") != 14' in text
    assert "quick_check" in text
    assert "foreign_key_check" in text
    assert "bash scripts/smoke-core.sh" in helper
    assert 'CORE_ENVIRONMENT="${RELEASE_STATE_DIR}/core-environment"' in helper
    assert '"${UV_COMMAND}" venv' in helper
    assert '"${UV_COMMAND}" pip install' in helper
    assert "--no-project" in helper
    assert '--editable "${ROOT}/apps/core[dev]"' in helper
    assert "\n  --project " not in helper
    assert "--locked" not in helper
    assert 'export CORE_PYTHON="${CORE_ENVIRONMENT}/bin/python"' in helper
    assert 'export ZIGBEELENS_CORE_PYTHON="${CORE_PYTHON}"' in helper
    assert 'CORE_RUFF="${CORE_ENVIRONMENT}/bin/ruff"' in helper
    assert '"${CORE_RUFF}" check src tests' in helper
    core_project = tomllib.loads(
        (ROOT / "apps" / "core" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert core_project["tool"]["ruff"]["lint"]["select"] == [
        "E4",
        "E7",
        "E9",
        "F",
    ]
    assert '"${CORE_PYTHON}" -m pytest -q' in addon_validator


def test_tracked_files_only_checkout_runs_real_smoke_without_local_state(
    tmp_path: Path,
) -> None:
    repository = _tracked_files_repository(tmp_path)
    script = repository / "scripts" / "smoke-core.sh"
    env, tmp_parent = _environment(tmp_path)
    env["PATH"] = "/usr/bin:/bin"
    assert shutil.which("uv", path=env["PATH"]) is None
    package_before = (
        repository / "apps" / "core" / "pyproject.toml"
    ).read_bytes()
    source_before = (
        repository / "apps" / "core" / "src" / "zigbeelens" / "__init__.py"
    ).read_bytes()
    config_path = repository / "config" / "config.yaml"
    config_before = config_path.read_bytes()

    result = _run(script, env=env, timeout=60)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core smoke Python owner: explicit" in result.stdout
    assert "OK: smoke-core passed" in result.stdout
    assert not (repository / "apps" / "core" / "uv.lock").exists()
    assert not (repository / "apps" / "core" / ".venv").exists()
    assert config_path.read_bytes() == config_before
    assert not (repository / "data").exists()
    assert (
        repository / "apps" / "core" / "pyproject.toml"
    ).read_bytes() == package_before
    assert (
        repository / "apps" / "core" / "src" / "zigbeelens" / "__init__.py"
    ).read_bytes() == source_before
    _assert_no_state(tmp_parent)


def test_no_pip_venv_shapes_and_repeated_runs_leave_sentinels_untouched(
    tmp_path: Path,
) -> None:
    repository, script = _fixture_repository(tmp_path)
    env, tmp_parent = _environment(tmp_path)
    env.update(
        {
            "ZIGBEELENS_MQTT_PASSWORD_FILE": str(tmp_path / "must-not-be-read"),
            "ZIGBEELENS_OPENAPI_ENABLED": "true",
            "ZIGBEELENS_SECURITY_API_TOKEN_FILE": str(tmp_path / "must-not-be-read"),
            "ZIGBEELENS_SECURITY_MODE": "home_assistant_ingress",
            "ZIGBEELENS_STATIC_DIR": str(tmp_path / "must-not-be-read"),
        }
    )
    config_before = (repository / "config" / "config.yaml").read_bytes()
    data_before = (repository / "data" / "zigbeelens.sqlite").read_bytes()

    first = _run(script, env=env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Core smoke Python owner: explicit" in first.stdout
    _assert_no_state(tmp_parent)

    venv_bin = repository / "apps" / "core" / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(sys.executable)
    assert not (venv_bin / "pip").exists()
    second = _run(script, env=env)
    assert second.returncode == 0, second.stdout + second.stderr
    _assert_no_state(tmp_parent)

    (venv_bin / "python").unlink()
    (venv_bin / "python").symlink_to(repository / "missing-python")
    third = _run(script, env=env)
    assert third.returncode == 0, third.stdout + third.stderr
    _assert_no_state(tmp_parent)

    assert (repository / "config" / "config.yaml").read_bytes() == config_before
    assert (repository / "data" / "zigbeelens.sqlite").read_bytes() == data_before


def test_smoke_follows_fixture_canonical_version_metadata(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(
        tmp_path,
        package_version="9.8.7",
    )
    env, tmp_parent = _environment(tmp_path)

    result = _run(script, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "version=9.8.7" in result.stdout
    _assert_no_state(tmp_parent)


def test_smoke_rejects_health_and_version_disagreement(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(
        tmp_path,
        package_version="9.8.7",
        version_api_override="9.8.6",
    )
    env, tmp_parent = _environment(tmp_path)

    result = _run(script, env=env)

    assert result.returncode != 0
    assert "unexpected /api/version version" in result.stderr
    _assert_no_state(tmp_parent)


def test_explicit_python_precedes_uv_and_is_observably_used(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(tmp_path)
    marker = tmp_path / "python-invocations"
    wrapper = tmp_path / "explicit-python"
    _write_python_wrapper(wrapper, marker=marker)
    env, tmp_parent = _environment(tmp_path, python=str(wrapper))
    env["PATH"] = "/usr/bin:/bin"
    assert shutil.which("uv", path=env["PATH"]) is None

    result = _run(script, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core smoke Python owner: explicit" in result.stdout
    invocations = marker.read_text(encoding="utf-8")
    assert "/core.pid" in invocations
    _assert_no_state(tmp_parent)


@pytest.mark.parametrize("kind", ["non_executable", "import_failure", "ignores_args"])
def test_invalid_explicit_python_fails_closed(tmp_path: Path, kind: str) -> None:
    _repository, script = _fixture_repository(tmp_path)
    candidate = tmp_path / f"invalid-{kind}"
    if kind == "non_executable":
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    elif kind == "import_failure":
        candidate.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        candidate.chmod(0o755)
    else:
        candidate.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        candidate.chmod(0o755)
    env, tmp_parent = _environment(tmp_path, python=str(candidate))

    result = _run(script, env=env)

    assert result.returncode != 0
    assert "Core Python" in result.stderr
    _assert_no_state(tmp_parent)


def test_uv_owned_invocation_passes_without_pip_repair(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv is required by the canonical release owner"
    repository, script = _fixture_repository(tmp_path)
    broken_venv = repository / "apps" / "core" / ".venv"
    broken_bin = broken_venv / "bin"
    broken_bin.mkdir(parents=True)
    (broken_bin / "python").symlink_to(repository / "missing-python")
    sentinel = broken_venv / "must-remain-byte-identical"
    sentinel.write_bytes(b"ignored-environment-sentinel\n")
    before_entries = sorted(
        path.relative_to(broken_venv)
        for path in broken_venv.rglob("*")
    )
    env, tmp_parent = _environment(tmp_path, python=None)
    poisoned_environment = tmp_path / "must-not-become-project-environment"
    poisoned_virtual_environment = tmp_path / "must-not-become-active-environment"
    env.update(
        {
            "UV_ACTIVE": "1",
            "UV_CONFIG_FILE": str(tmp_path / "must-not-be-read.toml"),
            "UV_ENV_FILE": str(tmp_path / "must-not-be-read.env"),
            "UV_FROZEN": "1",
            "UV_LOCKED": "1",
            "UV_NO_CONFIG": "1",
            "UV_NO_DEV": "1",
            "UV_NO_EDITABLE": "1",
            "UV_NO_INSTALL_PROJECT": "1",
            "UV_NO_PROJECT": "1",
            "UV_NO_SYNC": "1",
            "UV_PROJECT": str(tmp_path / "wrong-project"),
            "UV_PROJECT_ENVIRONMENT": str(poisoned_environment),
            "UV_PYTHON": str(tmp_path / "missing-python"),
            "UV_WORKING_DIR": str(tmp_path / "wrong-working-directory"),
            "VIRTUAL_ENV": str(poisoned_virtual_environment),
        }
    )

    result = _run(script, env=env, timeout=180)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core smoke Python owner: uv" in result.stdout
    assert not (repository / "apps" / "core" / "uv.lock").exists()
    assert sentinel.read_bytes() == b"ignored-environment-sentinel\n"
    assert (broken_bin / "python").readlink() == repository / "missing-python"
    assert sorted(
        path.relative_to(broken_venv)
        for path in broken_venv.rglob("*")
    ) == before_entries
    assert not poisoned_environment.exists()
    assert not poisoned_virtual_environment.exists()
    _assert_no_state(tmp_parent)


def test_missing_uv_and_unusable_python3_fail_clearly(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
    fake_python.chmod(0o755)
    env, tmp_parent = _environment(tmp_path, python=None)
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"

    result = _run(script, env=env)

    assert result.returncode != 0
    assert "python3 Core Python cannot import this checkout and uvicorn" in result.stderr
    _assert_no_state(tmp_parent)


def test_usable_python3_fallback_passes_without_uv(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_python_wrapper(fake_bin / "python3")
    env, tmp_parent = _environment(tmp_path, python=None)
    env["PATH"] = f"{fake_bin}:/usr/bin:/bin"

    result = _run(script, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core smoke Python owner: python3" in result.stdout
    _assert_no_state(tmp_parent)


def test_occupied_explicit_port_fails_before_startup_and_cleans_state(
    tmp_path: Path,
) -> None:
    _repository, script = _fixture_repository(tmp_path)
    env, tmp_parent = _environment(tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        env["SMOKE_PORT"] = str(listener.getsockname()[1])
        result = _run(script, env=env)

    assert result.returncode != 0
    assert "Core smoke port is unavailable" in result.stderr
    assert "starting isolated Core" not in result.stdout
    _assert_no_state(tmp_parent)


def test_pre_readiness_exit_prints_safe_log_and_cleans_state(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(tmp_path)
    wrapper = tmp_path / "startup-failure-python"
    _write_python_wrapper(wrapper, server="exit")
    env, tmp_parent = _environment(tmp_path, python=str(wrapper))

    result = _run(script, env=env)

    assert result.returncode != 0
    assert "forced safe startup failure" in result.stderr
    assert "Core exited before" in result.stderr
    _assert_no_state(tmp_parent)


def test_sigterm_kills_exact_explicit_child_and_removes_state(
    tmp_path: Path,
) -> None:
    _repository, script = _fixture_repository(tmp_path)
    wrapper = tmp_path / "term-ignoring-python"
    child_pid_path = tmp_path / "child.pid"
    _write_python_wrapper(
        wrapper,
        server="ignore-term",
        child_pid=child_pid_path,
    )
    env, tmp_parent = _environment(tmp_path, python=str(wrapper))
    locks_before = _lock_snapshot(script)
    process = subprocess.Popen(
        ["/bin/bash", str(script)],
        cwd=script.parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while not child_pid_path.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert child_pid_path.exists(), process.communicate(timeout=1)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    # Let the smoke parent consume the already-published PID before interrupting
    # it; the behavior under test is cleanup after ownership is established.
    time.sleep(0.2)

    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 143, stdout + stderr
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    _assert_locks_unchanged(locks_before)
    _assert_no_state(tmp_parent)


def test_sigterm_kills_exact_uv_grandchild_and_reaps_runner(
    tmp_path: Path,
) -> None:
    _repository, script = _fixture_repository(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    child_pid_path = tmp_path / "uv-child.pid"
    _write_uv_process_runner(fake_bin / "uv", child_pid_path)
    env, tmp_parent = _environment(tmp_path, python=None)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    locks_before = _lock_snapshot(script)
    process = subprocess.Popen(
        ["/bin/bash", str(script)],
        cwd=script.parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while not child_pid_path.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert child_pid_path.exists(), process.communicate(timeout=1)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    # Let the smoke parent consume the already-published PID before interrupting
    # it; the behavior under test is cleanup after ownership is established.
    time.sleep(0.2)

    process.send_signal(signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 143, stdout + stderr
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    _assert_locks_unchanged(locks_before)
    _assert_no_state(tmp_parent)
