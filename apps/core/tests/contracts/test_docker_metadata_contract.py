"""Fail-closed contracts for release identity in Docker image metadata."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "docker.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
BUILD_SCRIPT = ROOT / "scripts" / "build-docker.sh"
SMOKE_SCRIPT = ROOT / "scripts" / "smoke-docker.sh"
RELEASE_SCRIPT = ROOT / "scripts" / "run-release-checks.sh"
DOCKERFILE = ROOT / "deploy" / "docker" / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"
GITIGNORE = ROOT / ".gitignore"
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
SMOKE_STATE_GLOB = "zigbeelens-docker-smoke.*"
FAKE_IMAGE_ID = f"sha256:{'1' * 64}"
FAKE_CONTAINER_ID = "c" * 64

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
    include_dockerignore: bool = True,
) -> tuple[Path, Path, Path]:
    checkout = tmp_path / "checkout"
    scripts = checkout / "scripts"
    docker_dir = checkout / "deploy" / "docker"
    core_source = checkout / "apps" / "core" / "src" / "zigbeelens"
    ui_source = checkout / "apps" / "ui" / "src"
    shared_source = checkout / "packages" / "shared" / "src"
    scripts.mkdir(parents=True)
    docker_dir.mkdir(parents=True)
    core_source.mkdir(parents=True)
    ui_source.mkdir(parents=True)
    shared_source.mkdir(parents=True)
    shutil.copy2(BUILD_SCRIPT, scripts / "build-docker.sh")
    shutil.copy2(DOCKERFILE, docker_dir / "Dockerfile")
    shutil.copy2(GITIGNORE, checkout / ".gitignore")
    if include_dockerignore:
        shutil.copy2(DOCKERIGNORE, checkout / ".dockerignore")
    (core_source / "release_fixture.py").write_text(
        'RELEASE_FIXTURE = "core"\n',
        encoding="utf-8",
    )
    (ui_source / "release-fixture.ts").write_text(
        'export const releaseFixture = "ui";\n',
        encoding="utf-8",
    )
    (shared_source / "release-fixture.ts").write_text(
        'export const releaseFixture = "shared";\n',
        encoding="utf-8",
    )
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
        'printf "%s\\n" "$@" > "${DOCKER_ARGS_FILE:?}"\n'
        'context="${@: -1}"\n'
        'if [[ -d "${context}" ]]; then\n'
        "  (\n"
        '    cd "${context}"\n'
        '    find . -type f -print | LC_ALL=C sort\n'
        '  ) > "${DOCKER_CONTEXT_FILES:?}"\n'
        "fi\n",
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
        "ZIGBEELENS_SOURCE_EXPORT",
        "ZIGBEELENS_VERSION",
    ):
        build_environment.pop(name, None)
    build_environment.update(
        {
            "DOCKER_ARGS_FILE": str(docker_args),
            "DOCKER_CONTEXT_FILES": str(
                docker_args.with_name("docker-context-files")
            ),
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


def _write_fake_docker(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json
import os
from pathlib import Path
import shutil
import sys

state = Path(os.environ["FAKE_DOCKER_STATE"])
state.mkdir(parents=True, exist_ok=True)
args = sys.argv[1:]
with (state / "commands.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\n")

image_id = os.environ.get("FAKE_IMAGE_ID", "sha256:" + ("1" * 64))
container_id = os.environ.get("FAKE_CONTAINER_ID", "c" * 64)

if args == ["info"]:
    if os.environ.get("FAKE_DOCKER_INFO_FAILURE") == "1":
        print("controlled daemon failure", file=sys.stderr)
        raise SystemExit(71)
    print("controlled docker daemon")
    raise SystemExit(0)

if args[:2] == ["image", "inspect"]:
    template = args[-1]
    if ".Id" in template:
        print(image_id)
    elif "org.opencontainers.image.version" in template:
        print(os.environ.get("FAKE_IMAGE_VERSION", "0.1.14"))
    elif "org.opencontainers.image.revision" in template:
        print(
            os.environ.get(
                "FAKE_IMAGE_REVISION",
                os.environ["FAKE_EXPECTED_REVISION"],
            )
        )
    elif "org.opencontainers.image.source" in template:
        print(
            os.environ.get(
                "FAKE_IMAGE_SOURCE",
                "https://github.com/theaussiepom/zigbeelens",
            )
        )
    elif ".Config.User" in template:
        print(os.environ.get("FAKE_IMAGE_USER", "zigbeelens"))
    else:
        print("unsupported image inspect template", file=sys.stderr)
        raise SystemExit(64)
    raise SystemExit(0)

if args and args[0] == "run":
    (state / "run-args.json").write_text(
        json.dumps(args, indent=2) + "\n",
        encoding="utf-8",
    )
    (state / "removed").unlink(missing_ok=True)
    mode = os.environ.get("FAKE_DOCKER_RUN_MODE", "success")

    cid_path = None
    config_dir = None
    data_dir = None
    container_name = None
    owner_label = None
    for index, argument in enumerate(args):
        if argument == "--cidfile":
            cid_path = Path(args[index + 1])
        elif argument == "--name":
            container_name = args[index + 1]
        elif argument == "--label":
            key, value = args[index + 1].split("=", 1)
            if key == "com.zigbeelens.smoke.owner":
                owner_label = value
        if argument != "--mount":
            continue
        fields = {}
        for item in args[index + 1].split(","):
            if "=" in item:
                key, value = item.split("=", 1)
                fields[key] = value
        destination = fields.get("dst")
        if destination == "/config":
            config_dir = Path(fields["src"])
        elif destination == "/data":
            data_dir = Path(fields["src"])
    if (
        cid_path is None
        or config_dir is None
        or data_dir is None
        or container_name is None
        or owner_label is None
    ):
        print("controlled Docker did not receive owned smoke mounts", file=sys.stderr)
        raise SystemExit(73)

    (state / "container-name").write_text(container_name + "\n", encoding="utf-8")
    (state / "owner-label").write_text(owner_label + "\n", encoding="utf-8")
    if mode == "start-fail":
        print("controlled container start failure", file=sys.stderr)
        raise SystemExit(72)
    if mode == "block-before-cid":
        Path(os.environ["FAKE_DOCKER_RUN_BLOCK_MARKER"]).write_text(
            "blocked\n",
            encoding="utf-8",
        )
        import time

        time.sleep(30)
        raise SystemExit(77)

    # Docker Desktop writes the cidfile without a trailing newline. The smoke
    # must accept the populated final line even though Bash `read` returns EOF.
    cid_path.write_text(container_id, encoding="utf-8")
    (state / "config-copy.yaml").write_bytes(
        (config_dir / "config.yaml").read_bytes()
    )
    (state / "mounts.json").write_text(
        json.dumps(
            {
                "config": str(config_dir),
                "data": str(data_dir),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "zigbeelens.sqlite").write_bytes(b"controlled sqlite smoke\n")
    print(container_id)
    if mode == "start-fail-after-cid":
        print("controlled failure after container creation", file=sys.stderr)
        raise SystemExit(74)
    raise SystemExit(0)

if args and args[0] == "inspect":
    if len(args) == 2:
        if (
            os.environ.get("FAKE_DOCKER_NAME_COLLISION") == "1"
            and args[1].startswith("zigbeelens-smoke-")
        ):
            print(container_id)
            raise SystemExit(0)
        if (
            os.environ.get("FAKE_DOCKER_INSPECT_REMAINS") == "1"
            and args[1] == container_id
        ):
            print(container_id)
            raise SystemExit(0)
        raise SystemExit(1)
    target = args[1]
    template = args[-1]
    recorded_name_path = state / "container-name"
    recorded_name = (
        recorded_name_path.read_text(encoding="utf-8").strip()
        if recorded_name_path.exists()
        else ""
    )
    if target == recorded_name and ".Id" in template:
        print(container_id)
    elif target == recorded_name and "com.zigbeelens.smoke.owner" in template:
        owner = (state / "owner-label").read_text(encoding="utf-8").strip()
        print(os.environ.get("FAKE_DOCKER_OWNER_LABEL", owner))
    elif ".Image" in template:
        print(os.environ.get("FAKE_CONTAINER_IMAGE_ID", image_id))
    elif ".State.Running" in template:
        stopped = (
            os.environ.get("FAKE_DOCKER_EARLY_EXIT") == "1"
            or (state / "removed").exists()
        )
        print("false" if stopped else "true")
    else:
        print("unsupported container inspect template", file=sys.stderr)
        raise SystemExit(64)
    raise SystemExit(0)

if args and args[0] == "port":
    print(
        "127.0.0.1:"
        + os.environ.get(
            "FAKE_DOCKER_PORT",
            os.environ.get("SMOKE_DOCKER_PORT", "49152"),
        )
    )
    raise SystemExit(0)

if args and args[0] == "logs":
    if os.environ.get("FAKE_DOCKER_LOGS_FAILURE") == "1":
        print("controlled Docker log-read failure", file=sys.stderr)
        raise SystemExit(76)
    print(
        os.environ.get(
            "FAKE_DOCKER_LOG",
            "MQTT collector disabled (mock=True)\n"
            "api_token_configured=False credentialed_cors_enabled=False",
        )
    )
    raise SystemExit(0)

if args[:2] == ["rm", "-f"]:
    if os.environ.get("FAKE_DOCKER_RM_FAILURE") == "1":
        print("controlled container removal failure", file=sys.stderr)
        raise SystemExit(75)
    with (state / "removed-ids").open("a", encoding="utf-8") as stream:
        stream.write(args[2] + "\n")
    (state / "removed").write_text("removed\n", encoding="utf-8")
    raise SystemExit(0)

print("unsupported controlled Docker invocation: " + repr(args), file=sys.stderr)
raise SystemExit(64)
""".lstrip(),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_curl(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        + r"""
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

state = Path(os.environ["FAKE_DOCKER_STATE"])
args = sys.argv[1:]
with (state / "curl-commands.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(args) + "\n")

url = next((argument for argument in reversed(args) if argument.startswith("http://")), "")
if not url:
    print("controlled curl received no URL", file=sys.stderr)
    raise SystemExit(64)
path = urlsplit(url).path
if os.environ.get("FAKE_CURL_MODE") == "timeout":
    print("controlled readiness failure", file=sys.stderr)
    raise SystemExit(22)

version = os.environ.get("FAKE_API_VERSION", "0.1.14")
v1_version = os.environ.get("FAKE_API_V1_VERSION", version)
migration = int(os.environ.get("FAKE_API_MIGRATION", "15"))
schema = int(os.environ.get("FAKE_API_SCHEMA", "15"))

if path == "/":
    print("<!doctype html><title>ZigbeeLens</title>")
    raise SystemExit(0)
if path == "/healthz":
    payload = {"status": "ok"}
elif path == "/api/version":
    payload = {"version": version, "name": "zigbeelens-core"}
elif path == "/api/v1/version":
    payload = {"version": v1_version, "name": "zigbeelens-core"}
elif path == "/api/health":
    payload = {
        "status": "ok",
        "version": version,
        "config_loaded": True,
        "mock_mode": True,
        "database": "ok",
        "migration_version": migration,
        "collector": {"enabled": False, "connected": False},
        "mqtt_discovery": {"enabled": False, "connected": False},
        "topology": {
            "enabled": False,
            "manual_capture_enabled": False,
            "automatic_capture_enabled": False,
            "capture_in_progress": False,
            "networks": [
                {
                    "network_id": "docker-smoke",
                    "network_name": "Docker smoke",
                    "latest_snapshot": None,
                }
            ],
        },
    }
elif path == "/api/storage/status":
    payload = {
        "footprint": {"schema_version": schema},
        "integrity": {
            "quick_check": {"status": "ok", "violation_count": 0},
            "foreign_key_check": {"status": "ok", "violation_count": 0},
        },
    }
elif path == "/api/config/status":
    payload = {
        "version": version,
        "data_mode": "mock",
        "storage_path": "/data/zigbeelens.sqlite",
        "features": {
            "mqtt_collector": False,
            "mqtt_discovery": False,
            "device_payload_history": False,
            "manual_network_map": False,
            "automatic_network_map": False,
        },
        "mqtt_discovery": {"enabled": False},
        "topology": {
            "enabled": False,
            "startup_scan": False,
            "refresh_interval_seconds": 0,
            "manual_capture_enabled": False,
            "automatic_capture_enabled": False,
            "capture_on_incident": False,
        },
        "configured_networks": [
            {
                "id": "docker-smoke",
                "name": "Docker smoke",
                "base_topic": "zigbeelens-docker-smoke-unused",
            }
        ],
        "security": {
            "mode": "local",
            "api_token_configured": False,
            "session_secret_configured": False,
        },
    }
else:
    print("controlled curl received unsupported path: " + path, file=sys.stderr)
    raise SystemExit(22)

if os.environ.get("FAKE_CURL_EMPTY_PATH") == path:
    payload = {}
json.dump(payload, sys.stdout, separators=(",", ":"))
print()
""".lstrip(),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_sleep(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "${FAKE_SLEEP_BLOCK:-0}" = "1" ]; then\n'
        '  : > "${FAKE_SLEEP_MARKER:?}"\n'
        "  exec /bin/sleep 30\n"
        "fi\n"
        "exec /bin/sleep 0.05\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _docker_smoke_fixture(tmp_path: Path) -> dict[str, Any]:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    smoke = scripts / "smoke-docker.sh"
    shutil.copy2(SMOKE_SCRIPT, smoke)

    build = scripts / "build-docker.sh"
    build.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"\n'
        "git -C \"${ROOT}\" status --porcelain=v1 --untracked-files=all "
        '--ignore-submodules=none >"${FAKE_BUILD_STATUS:?}"\n'
        'printf "%s\\n" "${ZIGBEELENS_IMAGE:-}" >>"${FAKE_BUILD_CALLS:?}"\n'
        'if [[ -s "${FAKE_BUILD_STATUS}" ]]; then\n'
        '  cat "${FAKE_BUILD_STATUS}" >&2\n'
        '  echo "ERROR: canonical Docker builds require a clean Git source tree" >&2\n'
        "  exit 1\n"
        "fi\n",
        encoding="utf-8",
    )
    build.chmod(0o755)

    (repository / "package.json").write_text(
        json.dumps(
            {
                "name": "zigbeelens-docker-smoke-contract",
                "version": PACKAGE_VERSION,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repository / ".gitignore").write_text(
        "ignored-artifacts/\n"
        "tmp-under-checkout/\n",
        encoding="utf-8",
    )
    config_sentinel = repository / "config" / "config.yaml"
    config_sentinel.parent.mkdir()
    config_sentinel.write_bytes(b"repository config sentinel\n")
    data_sentinel = repository / "data" / "zigbeelens.sqlite"
    data_sentinel.parent.mkdir()
    data_sentinel.write_bytes(b"repository data sentinel\n")
    revision = _initialise_git_checkout(repository)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_docker(fake_bin / "docker")
    _write_fake_curl(fake_bin / "curl")
    _write_fake_sleep(fake_bin / "sleep")
    (fake_bin / "dirname").symlink_to(shutil.which("dirname") or "/usr/bin/dirname")
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        'if [ "${1:-}" = "-" ] && [ "$#" -eq 2 ]; then\n'
        '  if [ "${FAKE_PYTHON_PORT_UNAVAILABLE:-0}" = "1" ]; then\n'
        "    exit 1\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        f'exec "{sys.executable}" "$@"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)

    fake_state = tmp_path / "fake-docker-state"
    fake_state.mkdir()
    tmp_parent = tmp_path / "temporary-state"
    tmp_parent.mkdir()
    return {
        "repository": repository,
        "smoke": smoke,
        "fake_bin": fake_bin,
        "fake_state": fake_state,
        "tmp_parent": tmp_parent,
        "revision": revision,
        "config_sentinel": config_sentinel,
        "data_sentinel": data_sentinel,
    }


def _docker_smoke_environment(fixture: dict[str, Any]) -> dict[str, str]:
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name.startswith("FAKE_")
            or name.startswith("SMOKE_DOCKER_")
            or name in {"SMOKE_IMAGE", "ZIGBEELENS_REQUIRE_DOCKER"}
        ):
            environment.pop(name, None)
    fake_state = fixture["fake_state"]
    environment.update(
        {
            "PATH": f"{fixture['fake_bin']}{os.pathsep}{environment['PATH']}",
            "TMPDIR": str(fixture["tmp_parent"]),
            "ZIGBEELENS_REQUIRE_DOCKER": "1",
            "SMOKE_DOCKER_READINESS_TIMEOUT_SECONDS": "1",
            "FAKE_DOCKER_STATE": str(fake_state),
            "FAKE_EXPECTED_REVISION": str(fixture["revision"]),
            "FAKE_BUILD_CALLS": str(fake_state / "build-calls"),
            "FAKE_BUILD_STATUS": str(fake_state / "build-status"),
            "FAKE_SLEEP_MARKER": str(fake_state / "sleep-marker"),
            "FAKE_DOCKER_RUN_BLOCK_MARKER": str(
                fake_state / "docker-run-block-marker"
            ),
        }
    )
    return environment


def _run_docker_smoke(
    fixture: dict[str, Any],
    *,
    environment: dict[str, str] | None = None,
    timeout: float = 15,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(fixture["smoke"])],
        cwd=fixture["repository"],
        env=environment or _docker_smoke_environment(fixture),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _assert_no_docker_smoke_state(fixture: dict[str, Any]) -> None:
    assert list(fixture["tmp_parent"].glob(SMOKE_STATE_GLOB)) == []


def _json_lines(path: Path) -> list[Any]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _assert_docker_smoke_contract(smoke: str) -> None:
    assert ".smoke-config" not in smoke
    assert ".smoke-data" not in smoke
    assert smoke.count(
        'ZIGBEELENS_IMAGE="${IMAGE}" "${ROOT}/scripts/build-docker.sh"'
    ) == 1
    assert "docker build" not in smoke
    assert 'mktemp -d "${TMP_BASE}/zigbeelens-docker-smoke.XXXXXX"' in smoke
    assert '"${ROOT}/"*) fail "Docker smoke state must be outside' in smoke
    assert "ZIGBEELENS_REQUIRE_DOCKER:-1" in smoke
    assert '127.0.0.1:${PORT}:8377' in smoke
    assert "127.0.0.1::8377" in smoke
    assert "--read-only" in smoke
    assert "--cap-drop ALL" in smoke
    assert "--security-opt no-new-privileges:true" in smoke
    assert "--cidfile" in smoke
    assert 'CONTAINER_NAME="zigbeelens-smoke-${STATE_TOKEN}"' in smoke
    assert '--label "com.zigbeelens.smoke.owner=${STATE_TOKEN}"' in smoke
    assert smoke.index("CONTAINER_RUN_ATTEMPTED=1") < smoke.index(
        'if ! "${DOCKER_COMMAND}" run'
    )
    assert smoke.count(
        '--format \'{{ index .Config.Labels "com.zigbeelens.smoke.owner" }}\''
    ) == 1
    assert 'if [[ ! "${IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]; then' in smoke
    assert "docker.sock" not in smoke
    assert "--privileged" not in smoke
    assert "--network host" not in smoke
    assert "default_scenario: four_devices_same_room_unavailable" in smoke
    assert smoke.count("if ! capture_container_log; then") == 1
    assert smoke.count(
        'fail "unable to capture Docker smoke logs for external-activity checks"'
    ) == 1
    assert smoke.count(
        'if ! "${DOCKER_COMMAND}" rm -f "${CONTAINER_ID}" >/dev/null 2>&1; then'
    ) == 1
    assert smoke.count(
        'elif "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" '
        ">/dev/null 2>&1; then"
    ) == 1
    assert smoke.count('rm -rf -- "${STATE_DIR}"') == 1
    assert smoke.count("SMOKE_SUCCEEDED=1") == 1
    required_fetches = (
        'fetch_endpoint "health" "/healthz" "${HEALTHZ_PATH}"',
        'fetch_endpoint "version" "/api/version" "${VERSION_PATH}"',
        'fetch_endpoint "v1 version" "/api/v1/version" "${VERSION_V1_PATH}"',
        'fetch_endpoint "API health" "/api/health" "${API_HEALTH_PATH}"',
        (
            'fetch_endpoint "storage status" "/api/storage/status" '
            '"${STORAGE_STATUS_PATH}"'
        ),
        (
            'fetch_endpoint "config status" "/api/config/status" '
            '"${CONFIG_STATUS_PATH}"'
        ),
        'fetch_endpoint "bundled UI" "/" "${UI_ROOT_PATH}"',
    )
    for fetch in required_fetches:
        assert smoke.count(fetch) == 1
    assert '"${PYTHON_COMMAND}" -I -' in smoke
    assert "def require(condition: bool, message: str) -> None:" in smoke
    required_runtime_checks = (
        'require(healthz == {"status": "ok"}, "/healthz status")',
        'version == {"version": expected_version, "name": "zigbeelens-core"}',
        'require(version_v1 == version, "/api/v1/version parity")',
        'require(api_health["migration_version"] == 15, "/api/health migration")',
        'require(storage["footprint"]["schema_version"] == 15, "storage schema")',
        'config["storage_path"] == "/data/zigbeelens.sqlite"',
        'require(config["features"]["mqtt_collector"] is False, "config collector")',
        'require(config["features"]["mqtt_discovery"] is False, "config Discovery")',
        'config["features"]["manual_network_map"] is False',
        'config["features"]["automatic_network_map"] is False',
        'config["mqtt_discovery"]["enabled"] is False',
        'require(config["topology"]["enabled"] is False, "config topology")',
        'require(config["topology"]["startup_scan"] is False, "config startup capture")',
        'config["topology"]["refresh_interval_seconds"] == 0',
        'config["security"]["api_token_configured"] is False',
        'require("<title>ZigbeeLens</title>" in ui_root, "bundled UI identity")',
    )
    for check in required_runtime_checks:
        assert smoke.count(check) == 1


def _assert_release_docker_smoke_contract(helper: str) -> None:
    heading = 'echo "==> Standalone Docker image smoke"'
    command = "ZIGBEELENS_REQUIRE_DOCKER=1 bash scripts/smoke-docker.sh"
    success = 'echo "All automated release checks passed."'
    core_smoke = "bash scripts/smoke-core.sh"
    assert helper.count(heading) == 1
    assert helper.count(command) == 1
    assert helper.index(core_smoke) < helper.index(heading)
    assert helper.index(heading) < helper.index(command) < helper.index(success)
    block = helper[helper.index(heading) : helper.index(success)]
    for weakening in (
        "|| true",
        "continue-on-error",
        "ZIGBEELENS_REQUIRE_DOCKER=0",
        "SKIP:",
        "if false",
        "set +e",
    ):
        assert weakening not in block


def _expected_local_build_arguments(
    revision: str,
    *,
    context: str = ".",
    dockerfile: str = "deploy/docker/Dockerfile",
) -> list[str]:
    return [
        "build",
        "-f",
        dockerfile,
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
        context,
    ]


def _recorded_docker_arguments(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _assert_recorded_docker_arguments(
    path: Path,
    revision: str,
    *,
    source_export: bool = False,
) -> None:
    recorded = _recorded_docker_arguments(path)
    if source_export:
        assert recorded == _expected_local_build_arguments(revision)
        return
    context = Path(recorded[-1])
    assert context.is_absolute()
    assert context.name == "context"
    assert context.parent.name.startswith("zigbeelens-docker-context.")
    assert Path(recorded[2]) == context / "deploy" / "docker" / "Dockerfile"
    assert not context.exists()
    normalized = list(recorded)
    normalized[2] = "<committed-context>/deploy/docker/Dockerfile"
    normalized[-1] = "<committed-context>"
    assert normalized == _expected_local_build_arguments(
        revision,
        context="<committed-context>",
        dockerfile="<committed-context>/deploy/docker/Dockerfile",
    )


def _recorded_docker_context_files(path: Path) -> set[str]:
    context_files = path.with_name("docker-context-files")
    return set(context_files.read_text(encoding="utf-8").splitlines())


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
    _assert_recorded_docker_arguments(docker_args, revision)


def test_canonical_local_build_accepts_matching_git_revision_override(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"ZIGBEELENS_REVISION": revision},
    )

    assert result.returncode == 0, result.stderr
    _assert_recorded_docker_arguments(docker_args, revision)


def test_canonical_local_build_rejects_mismatched_git_revision_override(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    mismatched_revision = "a" * 40
    assert revision != mismatched_revision

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={"ZIGBEELENS_REVISION": mismatched_revision},
    )

    assert result.returncode != 0
    assert "must match the resolved Git HEAD" in result.stderr
    assert not docker_args.exists()


def test_canonical_source_export_requires_explicit_attestation(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = "a" * 40

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={
            "ZIGBEELENS_REVISION": revision,
            "ZIGBEELENS_SOURCE_EXPORT": "1",
        },
    )

    assert result.returncode == 0, result.stderr
    _assert_recorded_docker_arguments(
        docker_args,
        revision,
        source_export=True,
    )


@pytest.mark.parametrize(
    "attestation",
    (None, "", "true", "0"),
    ids=("unset", "empty", "truthy-word", "zero"),
)
def test_canonical_source_export_rejects_revision_without_exact_attestation(
    tmp_path: Path,
    attestation: str | None,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    environment = {"ZIGBEELENS_REVISION": "a" * 40}
    if attestation is not None:
        environment["ZIGBEELENS_SOURCE_EXPORT"] = attestation

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment=environment,
    )

    assert result.returncode != 0
    assert "requires ZIGBEELENS_SOURCE_EXPORT=1" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_fails_without_git_or_override(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode != 0
    assert "unable to resolve a Git revision" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_requires_maintained_root_dockerignore(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(
        tmp_path,
        include_dockerignore=False,
    )
    _initialise_git_checkout(checkout)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode != 0
    assert "requires the maintained root .dockerignore" in result.stderr
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

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={
            "ZIGBEELENS_REVISION": "a" * 40,
            "ZIGBEELENS_SOURCE_EXPORT": "1",
        },
    )

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
        environment={
            "ZIGBEELENS_REVISION": revision,
            "ZIGBEELENS_SOURCE_EXPORT": "1",
        },
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


def test_canonical_local_build_does_not_reclassify_failed_git_as_source_export(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={
            "ZIGBEELENS_REVISION": revision,
            "ZIGBEELENS_SOURCE_EXPORT": "1",
        },
    )

    assert result.returncode != 0
    assert (
        "Git metadata applies to the build root but Git revision resolution failed"
        in result.stderr
    )
    assert not docker_args.exists()


def test_canonical_source_export_rejects_failed_git_with_ancestor_metadata(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir()
    _git(parent, "init", "--quiet")
    checkout, fake_bin, docker_args = _local_build_fixture(parent)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment={
            "ZIGBEELENS_REVISION": "a" * 40,
            "ZIGBEELENS_SOURCE_EXPORT": "1",
        },
    )

    assert result.returncode != 0
    assert (
        "Git metadata applies to the build root but Git revision resolution failed"
        in result.stderr
    )
    assert not docker_args.exists()


def test_canonical_local_build_resolves_detached_head(tmp_path: Path) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    _git(checkout, "checkout", "--quiet", "--detach", revision)

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode == 0, result.stderr
    assert _git(checkout, "branch", "--show-current") == ""
    _assert_recorded_docker_arguments(docker_args, revision)


@pytest.mark.parametrize(
    ("relative_path", "stage_change", "use_revision_override"),
    (
        ("deploy/docker/Dockerfile", False, False),
        ("apps/core/src/zigbeelens/release_fixture.py", False, False),
        ("apps/ui/src/release-fixture.ts", False, False),
        ("packages/shared/src/release-fixture.ts", False, False),
        ("deploy/docker/Dockerfile", True, True),
    ),
    ids=(
        "modified-dockerfile",
        "modified-core-source",
        "modified-ui-source",
        "modified-shared-source",
        "staged-input",
    ),
)
def test_canonical_local_build_rejects_dirty_tracked_source_before_docker(
    tmp_path: Path,
    relative_path: str,
    stage_change: bool,
    use_revision_override: bool,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    source = checkout / relative_path
    source.write_text(
        source.read_text(encoding="utf-8") + "\n# dirty fixture\n",
        encoding="utf-8",
    )
    if stage_change:
        _git(checkout, "add", relative_path)
    assert _git(checkout, "status", "--short")
    environment = (
        {"ZIGBEELENS_REVISION": revision}
        if use_revision_override
        else None
    )

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment=environment,
    )

    assert result.returncode != 0
    assert "require a clean Git source tree" in result.stderr
    assert not docker_args.exists()


def test_canonical_local_build_rejects_untracked_copied_source_before_docker(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    _initialise_git_checkout(checkout)
    untracked_source = checkout / "apps" / "ui" / "src" / "untracked-release-input.ts"
    untracked_source.write_text(
        'export const untrackedReleaseInput = "unsafe";\n',
        encoding="utf-8",
    )
    assert "?? apps/ui/src/untracked-release-input.ts" in _git(
        checkout,
        "status",
        "--short",
    )

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode != 0
    assert "require a clean Git source tree" in result.stderr
    assert not docker_args.exists()


@pytest.mark.parametrize(
    ("ignore_owner", "relative_path"),
    (
        ("repository-local", "apps/ui/src/locally-hidden-release-input.ts"),
        ("global", "packages/shared/src/globally-hidden-release-input.ts"),
    ),
)
def test_canonical_local_build_archives_only_head_when_untracked_source_is_ignored(
    tmp_path: Path,
    ignore_owner: str,
    relative_path: str,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    hidden_source = checkout / relative_path
    hidden_source.write_text(
        'export const hiddenReleaseInput = "unsafe";\n',
        encoding="utf-8",
    )
    environment: dict[str, str] = {}
    if ignore_owner == "repository-local":
        info_exclude = checkout / ".git" / "info" / "exclude"
        info_exclude.write_text(
            info_exclude.read_text(encoding="utf-8")
            + f"\n{relative_path}\n",
            encoding="utf-8",
        )
    else:
        global_excludes = tmp_path / "global-excludes"
        global_excludes.write_text(f"{relative_path}\n", encoding="utf-8")
        global_config = tmp_path / "global-git-config"
        global_config.write_text(
            "[core]\n"
            f"\texcludesFile = {global_excludes}\n",
            encoding="utf-8",
        )
        environment.update(
            {
                "GIT_CONFIG_GLOBAL": str(global_config),
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )
    status_environment = os.environ.copy()
    status_environment.update(environment)
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=checkout,
        env=status_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""

    result = _run_local_build(
        checkout,
        fake_bin,
        docker_args,
        environment=environment,
    )

    assert result.returncode == 0, result.stderr
    _assert_recorded_docker_arguments(docker_args, revision)
    context_files = _recorded_docker_context_files(docker_args)
    assert f"./{relative_path}" not in context_files
    assert "./apps/ui/src/release-fixture.ts" in context_files
    assert "./packages/shared/src/release-fixture.ts" in context_files


def test_canonical_local_build_allows_ignored_generated_host_artifacts(
    tmp_path: Path,
) -> None:
    checkout, fake_bin, docker_args = _local_build_fixture(tmp_path)
    revision = _initialise_git_checkout(checkout)
    generated_paths = (
        "data/active.sqlite",
        ".venv/generated-marker",
        "node_modules/generated-marker",
        "apps/ui/node_modules/generated-marker",
        "apps/ui/dist/generated.js",
        "apps/ui/tsconfig.tsbuildinfo",
        "packages/shared/dist/generated.js",
        "apps/core/src/zigbeelens/__pycache__/generated.pyc",
        "apps/core/src/zigbeelens/generated.pyd",
        "apps/ui/src/generated.swp",
        "apps/addon/zigbeelens/.build/generated-marker",
        "dist/zigbeelens-hacs/generated-marker",
    )
    for relative_path in generated_paths:
        generated = checkout / relative_path
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("generated\n", encoding="utf-8")
    assert _git(checkout, "status", "--short") == ""

    result = _run_local_build(checkout, fake_bin, docker_args)

    assert result.returncode == 0, result.stderr
    _assert_recorded_docker_arguments(docker_args, revision)
    context_files = _recorded_docker_context_files(docker_args)
    for relative_path in generated_paths:
        assert f"./{relative_path}" not in context_files
    assert "./apps/ui/src/release-fixture.ts" in context_files
    assert "./packages/shared/src/release-fixture.ts" in context_files


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
    revision = _initialise_git_checkout(checkout)

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
    _assert_recorded_docker_arguments(docker_args, revision)


def test_root_dockerignore_excludes_generated_and_private_host_state() -> None:
    patterns = {
        line
        for raw_line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    }
    required_patterns = {
        ".git",
        ".git/**",
        "data/",
        "**/data/",
        "**/*.db",
        "**/*.sqlite",
        ".venv/",
        "**/.venv/",
        "venv/",
        "**/venv/",
        "node_modules/",
        "**/node_modules/",
        ".pnpm-store/",
        "dist/",
        "**/dist/",
        "build/",
        "**/build/",
        "apps/ui/dist/",
        "packages/shared/dist/",
        "apps/addon/zigbeelens/.build/",
        "**/.build/",
        "**/*.tsbuildinfo",
        "apps/core/uv.lock",
        "**/__pycache__/",
        "**/*.py[cod]",
        "**/*.pyc",
        "**/*.egg-info/",
        "**/.pytest_cache/",
        "**/.ruff_cache/",
        "**/.mypy_cache/",
        ".playwright/",
        "playwright-report/",
        "test-results/",
        "browser-profile/",
        "browser-profiles/",
        "captures/",
        "local/zigbeelens-test/",
        "**/*.log",
        "**/*.tmp",
        "**/*.swp",
        "**/*.tar",
        "**/*.tar.gz",
        "**/*.oci",
        ".DS_Store",
        ".idea/",
        ".vscode/",
    }

    assert required_patterns <= patterns
    assert not {pattern for pattern in patterns if pattern.startswith("!")}
    for required_source in (
        "package.json",
        "pnpm-workspace.yaml",
        "pnpm-lock.yaml",
        ".npmrc",
        "apps/core/src/",
        "apps/core/pyproject.toml",
        "apps/ui/src/",
        "apps/ui/package.json",
        "packages/shared/src/",
        "packages/shared/package.json",
        "deploy/docker/entrypoint.sh",
    ):
        assert required_source not in patterns
    excluded_tracked = set(
        _git(
            ROOT,
            "ls-files",
            "-ci",
            "--exclude-from=.dockerignore",
        ).splitlines()
    )
    required_tracked = set(
        _git(
            ROOT,
            "ls-files",
            "--",
            "package.json",
            "pnpm-workspace.yaml",
            "pnpm-lock.yaml",
            ".npmrc",
            "apps/core/pyproject.toml",
            "apps/core/README.md",
            "apps/core/src",
            "apps/ui",
            "packages/shared",
            "deploy/docker/entrypoint.sh",
        ).splitlines()
    )
    assert excluded_tracked.isdisjoint(required_tracked)


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


def test_docker_smoke_contract_is_hermetic_and_fail_closed() -> None:
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
    _assert_docker_smoke_contract(smoke)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            'ZIGBEELENS_IMAGE="${IMAGE}" "${ROOT}/scripts/build-docker.sh"',
            "true # canonical build removed",
        ),
        (
            'CONFIG_DIR="${STATE_DIR}/config"',
            'CONFIG_DIR="${ROOT}/.smoke-config"',
        ),
        (
            'fetch_endpoint "version" "/api/version" "${VERSION_PATH}"',
            'true # /api/version skipped',
        ),
        (
            'fetch_endpoint "v1 version" "/api/v1/version" "${VERSION_V1_PATH}"',
            'fetch_endpoint "v1 version" "/noop" "${VERSION_V1_PATH}"',
        ),
            (
                'require(version_v1 == version, "/api/v1/version parity")',
                'require(True, "/api/v1/version parity")',
            ),
            (
                (
                    'require(api_health["migration_version"] == 15, '
                    '"/api/health migration")'
                ),
                'require(True, "/api/health migration")',
            ),
            (
                (
                    'require(storage["footprint"]["schema_version"] == 15, '
                    '"storage schema")'
                ),
                'require(True, "storage schema")',
        ),
        (
            "--read-only",
            "--read-write",
        ),
        (
            "--cap-drop ALL",
            "--cap-add ALL",
        ),
        (
            '--label "com.zigbeelens.smoke.owner=${STATE_TOKEN}"',
            '--label "com.zigbeelens.smoke.owner=shared"',
        ),
        (
            'if [[ ! "${IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]]; then',
            'if [[ "${IMAGE_ID}" != sha256:* ]]; then',
        ),
        (
            "if ! capture_container_log; then",
            "if false; then",
        ),
        (
            (
                'elif "${DOCKER_COMMAND}" inspect "${CONTAINER_ID}" '
                ">/dev/null 2>&1; then"
            ),
            "elif false; then",
        ),
    ),
)
def test_docker_smoke_contract_rejects_required_gate_weakening(
    old: str,
    new: str,
) -> None:
    smoke = SMOKE_SCRIPT.read_text(encoding="utf-8")
    assert old in smoke
    with pytest.raises(AssertionError):
        _assert_docker_smoke_contract(smoke.replace(old, new, 1))


def test_docker_smoke_success_is_external_isolated_and_repeatable(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    repository = fixture["repository"]
    ignored = repository / "ignored-artifacts" / "generated-ui"
    ignored.parent.mkdir()
    ignored.write_bytes(b"ignored generated sentinel\n")
    config_before = fixture["config_sentinel"].read_bytes()
    data_before = fixture["data_sentinel"].read_bytes()

    first = _run_docker_smoke(fixture)
    second = _run_docker_smoke(fixture)

    for result in (first, second):
        assert result.returncode == 0, result.stdout + result.stderr
        assert "OK: smoke-docker passed" in result.stdout
        assert "schema=15 mqtt_attempts=0 topology_attempts=0" in result.stdout
    assert fixture["config_sentinel"].read_bytes() == config_before
    assert fixture["data_sentinel"].read_bytes() == data_before
    assert not (repository / ".smoke-config").exists()
    assert not (repository / ".smoke-data").exists()
    assert _git(repository, "status", "--short") == ""
    _assert_no_docker_smoke_state(fixture)

    fake_state = fixture["fake_state"]
    build_calls = (fake_state / "build-calls").read_text(encoding="utf-8").splitlines()
    assert build_calls == ["zigbeelens-smoke:local", "zigbeelens-smoke:local"]
    assert (fake_state / "build-status").read_text(encoding="utf-8") == ""
    removed = (fake_state / "removed-ids").read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID, FAKE_CONTAINER_ID]
    docker_commands = _json_lines(fake_state / "commands.jsonl")
    assert docker_commands.count(["inspect", FAKE_CONTAINER_ID]) == 2

    mounts = json.loads((fake_state / "mounts.json").read_text(encoding="utf-8"))
    tmp_parent = fixture["tmp_parent"].resolve()
    for mount in mounts.values():
        assert Path(mount).is_relative_to(tmp_parent)
        assert not Path(mount).is_relative_to(repository.resolve())
    config = yaml.safe_load(
        (fake_state / "config-copy.yaml").read_text(encoding="utf-8")
    )
    assert config["server"] == {"host": "0.0.0.0", "port": 8377}
    assert config["mode"] == {
        "mock": True,
        "default_scenario": "four_devices_same_room_unavailable",
    }
    assert config["security"] == {"mode": "local"}
    assert config["mqtt"]["server"] == ""
    assert config["mqtt"]["username"] == ""
    assert config["mqtt"]["password"] == ""
    assert config["storage"]["path"] == "/data/zigbeelens.sqlite"
    assert config["networks"] == [
        {
            "id": "docker-smoke",
            "name": "Docker smoke",
            "base_topic": "zigbeelens-docker-smoke-unused",
        }
    ]
    assert config["features"] == {
        "mqtt_collector": False,
        "mqtt_discovery": False,
        "bridge_logs": False,
        "device_payload_history": False,
        "manual_network_map": False,
        "automatic_network_map": False,
    }
    assert config["mqtt_discovery"] == {"enabled": False}
    assert config["topology"] == {
        "enabled": False,
        "startup_scan": False,
        "refresh_interval_seconds": 0,
        "manual_capture_enabled": False,
        "automatic_capture_enabled": False,
        "capture_on_incident": False,
    }

    run_args = json.loads((fake_state / "run-args.json").read_text(encoding="utf-8"))
    for required in (
        "--read-only",
        "--tmpfs",
        "--cap-drop",
        "--security-opt",
        "--cidfile",
    ):
        assert run_args.count(required) == 1
    assert run_args[run_args.index("--cap-drop") + 1] == "ALL"
    assert (
        run_args[run_args.index("--security-opt") + 1]
        == "no-new-privileges:true"
    )
    assert run_args[run_args.index("-p") + 1] == "127.0.0.1::8377"
    state_token = Path(mounts["config"]).parent.name.rsplit(".", 1)[1]
    assert run_args[run_args.index("--name") + 1] == (
        f"zigbeelens-smoke-{state_token}"
    )
    assert run_args[run_args.index("--label") + 1] == (
        f"com.zigbeelens.smoke.owner={state_token}"
    )
    joined_run = "\n".join(run_args)
    assert "docker.sock" not in joined_run
    assert "--privileged" not in run_args
    assert "network=host" not in joined_run

    curl_urls = {
        argument
        for command in _json_lines(fake_state / "curl-commands.jsonl")
        for argument in command
        if argument.startswith("http://")
    }
    assert {
        "http://127.0.0.1:49152/healthz",
        "http://127.0.0.1:49152/api/version",
        "http://127.0.0.1:49152/api/v1/version",
        "http://127.0.0.1:49152/api/health",
        "http://127.0.0.1:49152/api/storage/status",
        "http://127.0.0.1:49152/api/config/status",
        "http://127.0.0.1:49152/",
    } <= curl_urls


@pytest.mark.parametrize(
    "port",
    ("abc", "-1", "0", "65536", "1.5", " 8377"),
)
def test_docker_smoke_rejects_invalid_explicit_port_before_build_or_run(
    tmp_path: Path,
    port: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment["SMOKE_DOCKER_PORT"] = port

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "SMOKE_DOCKER_PORT must be an integer from 1 to 65535" in result.stderr
    assert not (fixture["fake_state"] / "build-calls").exists()
    assert not (fixture["fake_state"] / "run-args.json").exists()
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_rejects_occupied_explicit_port_before_build_or_run(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    port = 43123
    environment["SMOKE_DOCKER_PORT"] = str(port)
    environment["FAKE_PYTHON_PORT_UNAVAILABLE"] = "1"

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert f"SMOKE_DOCKER_PORT is unavailable on 127.0.0.1:{port}" in result.stderr
    assert not (fixture["fake_state"] / "build-calls").exists()
    assert not (fixture["fake_state"] / "run-args.json").exists()
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_explicit_port_is_loopback_only(tmp_path: Path) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    port = 43124
    environment["SMOKE_DOCKER_PORT"] = str(port)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode == 0, result.stdout + result.stderr
    run_args = json.loads(
        (fixture["fake_state"] / "run-args.json").read_text(encoding="utf-8")
    )
    assert run_args[run_args.index("-p") + 1] == f"127.0.0.1:{port}:8377"
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_strict_mode_fails_without_docker_command(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    (fixture["fake_bin"] / "docker").rename(fixture["fake_bin"] / "docker.disabled")
    environment = _docker_smoke_environment(fixture)
    environment["PATH"] = str(fixture["fake_bin"])

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "docker is required for the standalone image smoke" in result.stderr
    assert "SKIP:" not in result.stdout
    assert not (fixture["fake_state"] / "build-calls").exists()
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_strict_mode_fails_when_daemon_is_unavailable(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment["FAKE_DOCKER_INFO_FAILURE"] = "1"

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "docker daemon is required for the standalone image smoke" in result.stderr
    assert "SKIP:" not in result.stdout
    assert not (fixture["fake_state"] / "build-calls").exists()
    _assert_no_docker_smoke_state(fixture)


@pytest.mark.parametrize(
    ("environment_update", "expected_error"),
    (
        (
            {"FAKE_DOCKER_EARLY_EXIT": "1", "FAKE_DOCKER_LOG": "safe early exit"},
            "container exited before readiness",
        ),
        (
            {"FAKE_CURL_MODE": "timeout", "FAKE_DOCKER_LOG": "safe timeout log"},
            "readiness timed out",
        ),
        (
            {
                "FAKE_DOCKER_RUN_MODE": "start-fail-after-cid",
                "FAKE_DOCKER_LOG": "safe start failure",
            },
            "container failed to start",
        ),
    ),
    ids=("early-exit", "readiness-timeout", "start-failure-after-cid"),
)
def test_docker_smoke_failure_surfaces_safe_logs_and_cleans_owned_state(
    tmp_path: Path,
    environment_update: dict[str, str],
    expected_error: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment.update(environment_update)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert environment_update["FAKE_DOCKER_LOG"] in result.stderr
    removed = (
        fixture["fake_state"] / "removed-ids"
    ).read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID]
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_fails_when_required_log_capture_is_unavailable(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment["FAKE_DOCKER_LOGS_FAILURE"] = "1"

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "unable to capture Docker smoke logs" in result.stderr
    removed = (
        fixture["fake_state"] / "removed-ids"
    ).read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID]
    _assert_no_docker_smoke_state(fixture)


@pytest.mark.parametrize(
    ("environment_update", "expected_error"),
    (
        (
            {"FAKE_DOCKER_RM_FAILURE": "1"},
            "failed to remove Docker smoke container",
        ),
        (
            {"FAKE_DOCKER_INSPECT_REMAINS": "1"},
            "Docker smoke container still exists after cleanup",
        ),
    ),
    ids=("remove-failure", "post-remove-inspect-still-present"),
)
def test_docker_smoke_cleanup_fails_closed(
    tmp_path: Path,
    environment_update: dict[str, str],
    expected_error: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment.update(environment_update)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert "OK: smoke-docker passed" not in result.stdout
    _assert_no_docker_smoke_state(fixture)


@pytest.mark.parametrize(
    ("environment_update", "expected_error"),
    (
        ({"FAKE_IMAGE_ID": "sha256:not-lowercase-hex"}, "canonical image ID"),
        ({"FAKE_IMAGE_VERSION": "9.9.9"}, "OCI version mismatch"),
        ({"FAKE_IMAGE_REVISION": "a" * 40}, "OCI revision mismatch"),
        (
            {"FAKE_IMAGE_SOURCE": "https://github.com/example/fork"},
            "OCI source mismatch",
        ),
        ({"FAKE_IMAGE_USER": "root"}, "must run as the zigbeelens user"),
        (
            {"FAKE_CONTAINER_IMAGE_ID": f"sha256:{'2' * 64}"},
            "running container image ID",
        ),
    ),
    ids=(
        "malformed-image-id",
        "version-label",
        "revision-label",
        "source-label",
        "user",
        "image-id",
    ),
)
def test_docker_smoke_rejects_wrong_image_identity(
    tmp_path: Path,
    environment_update: dict[str, str],
    expected_error: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment.update(environment_update)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert expected_error in result.stderr
    _assert_no_docker_smoke_state(fixture)


@pytest.mark.parametrize(
    ("environment_update", "expected_error"),
    (
        ({"FAKE_API_VERSION": "9.9.9"}, "/api/version identity"),
        ({"FAKE_API_V1_VERSION": "9.9.9"}, "/api/v1/version parity"),
        ({"FAKE_API_MIGRATION": "14"}, "/api/health migration"),
        ({"FAKE_API_SCHEMA": "14"}, "storage schema"),
        ({"FAKE_CURL_EMPTY_PATH": "/api/version"}, "/api/version identity"),
    ),
    ids=("api-version", "api-prefix", "migration", "schema", "endpoint-noop"),
)
def test_docker_smoke_rejects_wrong_runtime_contract(
    tmp_path: Path,
    environment_update: dict[str, str],
    expected_error: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment.update(environment_update)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert f"Docker smoke runtime contract failed: {expected_error}" in result.stderr
    removed = (
        fixture["fake_state"] / "removed-ids"
    ).read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID]
    _assert_no_docker_smoke_state(fixture)


@pytest.mark.parametrize(
    "unsafe_log",
    (
        "MQTT connected to broker.invalid:1883",
        "MQTT connect failed rc=1",
        "MQTT discovery publisher connect failed rc=1",
        "Discovery publication attempted",
        "topology capture requested",
        "Traceback (most recent call last)",
        "Unhandled exception",
        "password=not-a-real-secret",
        "api_token=not-a-real-token",
        "api_key=not-a-real-key",
        "session_secret=not-a-real-session-secret",
        "credential=not-a-real-credential",
    ),
)
def test_docker_smoke_rejects_external_activity_or_sensitive_logs(
    tmp_path: Path,
    unsafe_log: str,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment["FAKE_DOCKER_LOG"] = unsafe_log

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "forbidden external activity or sensitive output" in result.stderr
    if unsafe_log.startswith(
        (
            "password=",
            "api_token=",
            "api_key=",
            "session_secret=",
            "credential=",
        )
    ):
        assert unsafe_log not in result.stderr
        assert "[sensitive-looking container log lines withheld]" in result.stderr
    else:
        assert unsafe_log in result.stderr
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_state_never_hides_an_unrelated_dirty_tree(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    dirty = fixture["repository"] / "unexpected-untracked.txt"
    dirty.write_text("must remain visible\n", encoding="utf-8")

    result = _run_docker_smoke(fixture)

    assert result.returncode != 0
    assert "canonical Docker builds require a clean Git source tree" in result.stderr
    assert "?? unexpected-untracked.txt" in result.stderr
    assert dirty.read_text(encoding="utf-8") == "must remain visible\n"
    assert not (fixture["fake_state"] / "run-args.json").exists()
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_rejects_tmpdir_inside_checkout_and_removes_state(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    tmp_under_checkout = fixture["repository"] / "tmp-under-checkout"
    tmp_under_checkout.mkdir()
    environment = _docker_smoke_environment(fixture)
    environment["TMPDIR"] = str(tmp_under_checkout)

    result = _run_docker_smoke(fixture, environment=environment)

    assert result.returncode != 0
    assert "Docker smoke state must be outside the Git checkout" in result.stderr
    assert list(tmp_under_checkout.glob(SMOKE_STATE_GLOB)) == []
    assert not (fixture["fake_state"] / "build-calls").exists()


def test_docker_smoke_sigterm_removes_exact_container_and_state(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment.update(
        {
            "FAKE_CURL_MODE": "timeout",
            "FAKE_SLEEP_BLOCK": "1",
            "SMOKE_DOCKER_READINESS_TIMEOUT_SECONDS": "300",
        }
    )
    process = subprocess.Popen(
        ["/bin/bash", str(fixture["smoke"])],
        cwd=fixture["repository"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    marker = fixture["fake_state"] / "sleep-marker"
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert marker.exists(), process.communicate(timeout=1)

    os.killpg(process.pid, signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 143, stdout + stderr
    removed = (
        fixture["fake_state"] / "removed-ids"
    ).read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID]
    _assert_no_docker_smoke_state(fixture)


def test_docker_smoke_sigterm_during_docker_run_uses_verified_name_fallback(
    tmp_path: Path,
) -> None:
    fixture = _docker_smoke_fixture(tmp_path)
    environment = _docker_smoke_environment(fixture)
    environment["FAKE_DOCKER_RUN_MODE"] = "block-before-cid"
    process = subprocess.Popen(
        ["/bin/bash", str(fixture["smoke"])],
        cwd=fixture["repository"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    marker = fixture["fake_state"] / "docker-run-block-marker"
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        if process.poll() is not None:
            break
        time.sleep(0.02)
    assert marker.exists(), process.communicate(timeout=1)

    os.killpg(process.pid, signal.SIGTERM)
    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 143, stdout + stderr
    removed = (
        fixture["fake_state"] / "removed-ids"
    ).read_text(encoding="utf-8").splitlines()
    assert removed == [FAKE_CONTAINER_ID]
    docker_commands = _json_lines(
        fixture["fake_state"] / "commands.jsonl"
    )
    assert any(
        command[0] == "inspect"
        and ".Id" in command[-1]
        and command[1].startswith("zigbeelens-smoke-")
        for command in docker_commands
    )
    assert any(
        command[0] == "inspect"
        and "com.zigbeelens.smoke.owner" in command[-1]
        for command in docker_commands
    )
    _assert_no_docker_smoke_state(fixture)


def test_release_helper_owns_exact_strict_docker_smoke_once() -> None:
    _assert_release_docker_smoke_contract(
        RELEASE_SCRIPT.read_text(encoding="utf-8")
    )


@pytest.mark.parametrize(
    ("old", "new"),
    (
        (
            "ZIGBEELENS_REQUIRE_DOCKER=1 bash scripts/smoke-docker.sh",
            "true # Docker smoke removed",
        ),
        (
            "ZIGBEELENS_REQUIRE_DOCKER=1 bash scripts/smoke-docker.sh",
            "ZIGBEELENS_REQUIRE_DOCKER=0 bash scripts/smoke-docker.sh",
        ),
        (
            "ZIGBEELENS_REQUIRE_DOCKER=1 bash scripts/smoke-docker.sh",
            (
                "ZIGBEELENS_REQUIRE_DOCKER=1 bash scripts/smoke-docker.sh "
                "|| true"
            ),
        ),
        (
            'echo "==> Standalone Docker image smoke"',
            'echo "==> Standalone Docker image smoke"\n'
            'echo "==> Standalone Docker image smoke"',
        ),
    ),
    ids=("no-op", "non-strict", "soft-fail", "duplicate"),
)
def test_release_helper_contract_rejects_skipped_or_softened_docker_smoke(
    old: str,
    new: str,
) -> None:
    helper = RELEASE_SCRIPT.read_text(encoding="utf-8")
    assert old in helper
    with pytest.raises(AssertionError):
        _assert_release_docker_smoke_contract(helper.replace(old, new, 1))


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
