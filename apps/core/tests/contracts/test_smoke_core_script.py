"""Hermetic ownership contract for the canonical Core smoke gate."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[4]
SMOKE = ROOT / "scripts" / "smoke-core.sh"
RELEASE_HELPER = ROOT / "scripts" / "run-release-checks.sh"
STATE_GLOB = "zigbeelens-core-smoke.*"


def _fixture_repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    script = repository / "scripts" / "smoke-core.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(SMOKE, script)

    core = repository / "apps" / "core"
    core.mkdir(parents=True)
    (core / "src").symlink_to(ROOT / "apps" / "core" / "src", target_is_directory=True)
    for project_file in ("pyproject.toml", "README.md", "uv.lock"):
        shutil.copy2(ROOT / "apps" / "core" / project_file, core / project_file)

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


def _run(
    script: Path,
    *,
    env: dict[str, str],
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(script)],
        cwd=script.parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


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

    assert "apps/core/.venv" not in text
    assert "source " not in text
    assert "pip install" not in text
    assert "config/config.yaml" not in text
    assert "./data/" not in text
    assert '"$UV_COMMAND" run' in text
    assert "--isolated" in text
    assert "--locked" in text
    assert "--no-config" in text
    assert "--no-env-file" in text
    assert "--project" in text
    assert "--extra dev" in text
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


def test_explicit_python_precedes_uv_and_is_observably_used(tmp_path: Path) -> None:
    _repository, script = _fixture_repository(tmp_path)
    marker = tmp_path / "python-invocations"
    wrapper = tmp_path / "explicit-python"
    _write_python_wrapper(wrapper, marker=marker)
    env, tmp_parent = _environment(tmp_path, python=str(wrapper))

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
            "UV_ENV_FILE": str(tmp_path / "must-not-be-read.env"),
            "UV_NO_PROJECT": "1",
            "UV_NO_SYNC": "1",
            "UV_PROJECT": str(tmp_path / "wrong-project"),
            "UV_PROJECT_ENVIRONMENT": str(poisoned_environment),
            "UV_PYTHON": str(tmp_path / "missing-python"),
            "UV_WORKING_DIR": str(tmp_path / "wrong-working-directory"),
            "VIRTUAL_ENV": str(poisoned_virtual_environment),
        }
    )

    result = _run(script, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Core smoke Python owner: uv" in result.stdout
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
    _assert_no_state(tmp_parent)
